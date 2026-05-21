import cv2
import itertools
import numpy as np


class SurveyProcessor:
    def __init__(self):
        self.last_error = ""

    # Corner markers of the printed form, in the original design space.
    CORNER_TL = (42, 53)
    CORNER_TR = (511, 53)
    CORNER_BL = (42, 724)
    CORNER_BR = (511, 724)

    # Warped image output size.
    WARP_W, WARP_H = 800, 1000

    # Exact bubble centres in the correctly oriented warped coordinate space.
    COL1_XS = [176, 205, 232, 261, 288]
    COL2_XS = [563, 592, 619, 648, 675]
    ROW_YS = [
        174, 224, 273, 319, 370,
        419, 468, 516, 563, 614,
        663, 711, 760, 808, 857,
    ]

    BUBBLE_RADIUS = 12
    MIN_MARK_PIXELS = 180
    MIN_MARK_GAP = 80
    MIN_MARK_RATIO = 1.35
    MIN_MARK_CONTRAST = 12
    MIN_ANSWERED = 5

    # Validation thresholds, now applied after warp/orientation correction.
    MIN_CIRCLES = 120
    MIN_GRID_SCORE = 80
    MAX_INK_RATIO = 0.50

    def _order_points(self, pts):
        """Return points in TL, TR, BR, BL image order."""
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect

    def _four_point_transform(self, gray, pts):
        dst = np.array(
            [
                [0, 0],
                [self.WARP_W, 0],
                [self.WARP_W, self.WARP_H],
                [0, self.WARP_H],
            ],
            dtype="float32",
        )
        m = cv2.getPerspectiveTransform(pts, dst)
        return cv2.warpPerspective(gray, m, (self.WARP_W, self.WARP_H))

    def find_survey_polygon(self, frame):
        """
        Detect the 4 black corner squares and return their centres as a
        (4,2) float32 array in TL/TR/BR/BL image order.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        markers = self._find_marker_candidates(gray)

        if len(markers) < 4:
            return None

        markers = np.array(markers, dtype="float32")
        if len(markers) > 4:
            markers = self._select_best_marker_quad(markers)

        return self._order_points(markers)

    def _find_marker_candidates(self, gray):
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        img_area = gray.shape[0] * gray.shape[1]
        min_area = max(500, img_area * 0.00025)
        max_area = img_area * 0.02
        markers = []

        # Real photos vary a lot in exposure, so try several dark thresholds.
        for threshold_value in (60, 80, 100, 120, 140, 160):
            _, thresh = cv2.threshold(
                blur,
                threshold_value,
                255,
                cv2.THRESH_BINARY_INV,
            )
            cnts, _ = cv2.findContours(
                thresh,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE,
            )

            for c in cnts:
                area = cv2.contourArea(c)
                if area < min_area or area > max_area:
                    continue

                x, y, w, h = cv2.boundingRect(c)
                aspect = w / float(h)
                extent = area / float(w * h)
                if not (0.65 <= aspect <= 1.55 and extent >= 0.65):
                    continue

                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.04 * peri, True)
                if len(approx) not in (4, 5):
                    continue

                m = cv2.moments(c)
                if m["m00"] == 0:
                    continue

                cx = int(m["m10"] / m["m00"])
                cy = int(m["m01"] / m["m00"])
                self._append_unique_marker(markers, (cx, cy), min(w, h) * 0.4)

        return markers

    def _append_unique_marker(self, markers, marker, min_distance):
        for existing in markers:
            if np.linalg.norm(np.array(existing) - np.array(marker)) < min_distance:
                return
        markers.append(marker)

    def _select_best_marker_quad(self, pts):
        """
        Pick the four candidates that form the largest plausible page corners.
        This rejects dark background objects in real photos.
        """
        best = None
        for combo in itertools.combinations(pts, 4):
            quad = self._order_points(np.array(combo, dtype="float32"))
            area = cv2.contourArea(quad)
            if area <= 0:
                continue

            top = np.linalg.norm(quad[1] - quad[0])
            right = np.linalg.norm(quad[2] - quad[1])
            bottom = np.linalg.norm(quad[2] - quad[3])
            left = np.linalg.norm(quad[3] - quad[0])
            if min(top, right, bottom, left) == 0:
                continue

            opposite_balance = min(top, bottom) / max(top, bottom)
            side_balance = min(left, right) / max(left, right)
            score = area * opposite_balance * side_balance

            if best is None or score > best[0]:
                best = (score, quad)

        if best is None:
            return self._order_points(pts)
        return best[1]

    def _survey_form_score(self, warped_gray, mirrored=False):
        """
        Score a candidate orientation.
        Real upright forms have lots of circular glyphs near the expected
        bubble centres and a reasonable amount of ink on white paper.
        """
        _, t200 = cv2.threshold(warped_gray, 200, 255, cv2.THRESH_BINARY_INV)
        ink_ratio = cv2.countNonZero(t200) / warped_gray.size
        circles = self._count_circular_glyphs(warped_gray)
        grid_score = self._bubble_grid_score(warped_gray, mirrored=mirrored)

        if ink_ratio < 0.005:
            return 0

        if ink_ratio > self.MAX_INK_RATIO and grid_score < self.MIN_GRID_SCORE:
            return 0

        if circles < self.MIN_CIRCLES and grid_score < self.MIN_GRID_SCORE:
            return 0

        return circles + grid_score

    def _count_circular_glyphs(self, warped_gray):
        _, t200 = cv2.threshold(warped_gray, 200, 255, cv2.THRESH_BINARY_INV)

        # Ignore the extreme edges and inspect the warped form body.
        margin_x = int(self.WARP_W * 0.05)
        margin_y = int(self.WARP_H * 0.05)
        content_mask = np.zeros_like(t200)
        content_mask[
            margin_y:self.WARP_H - margin_y,
            margin_x:self.WARP_W - margin_x,
        ] = t200[
            margin_y:self.WARP_H - margin_y,
            margin_x:self.WARP_W - margin_x,
        ]

        cnts, _ = cv2.findContours(
            content_mask,
            cv2.RETR_LIST,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        circle_count = 0
        for c in cnts:
            area = cv2.contourArea(c)
            if area < 30 or area > 2000:
                continue
            peri = cv2.arcLength(c, True)
            if peri == 0:
                continue
            circularity = (4 * np.pi * area) / (peri ** 2)
            if circularity > 0.50:
                circle_count += 1

        return circle_count

    def _bubble_grid_score(self, warped_gray, mirrored=False):
        """
        Expected bubble locations should contain printed dark pixels even when
        blank. Wrong rotations put those sample windows over mostly empty paper.
        """
        score = 0
        sample_points = []
        col1_xs, col2_xs = self._grid_xs(mirrored=mirrored)
        for ry in self.ROW_YS:
            sample_points.extend((cx, ry) for cx in col1_xs)
            sample_points.extend((cx, ry) for cx in col2_xs)

        for cx, cy in sample_points:
            score += min(self._read_bubble(warped_gray, cy, cx), 140)

        return score / 100.0

    def _is_valid_survey_form(self, warped_gray, mirrored=False):
        return self._survey_form_score(warped_gray, mirrored=mirrored) > 0

    def _grid_xs(self, mirrored=False):
        if not mirrored:
            return self.COL1_XS, self.COL2_XS

        col1_xs = [self.WARP_W - x for x in self.COL1_XS]
        col2_xs = [self.WARP_W - x for x in self.COL2_XS]
        return col1_xs, col2_xs

    def _read_results(self, warped_gray, mirrored=False):
        results = {}
        mark_score = 0
        col1_xs, col2_xs = self._grid_xs(mirrored=mirrored)

        for i, ry in enumerate(self.ROW_YS):
            q_num = i + 1
            metrics = [
                self._read_bubble_metrics(warped_gray, ry, cx)
                for cx in col1_xs
            ]
            results[q_num] = self._pick_choice(metrics)
            mark_score += max(metric["dark_pixels"] for metric in metrics)

            q_num = i + 16
            metrics = [
                self._read_bubble_metrics(warped_gray, ry, cx)
                for cx in col2_xs
            ]
            results[q_num] = self._pick_choice(metrics)
            mark_score += max(metric["dark_pixels"] for metric in metrics)

        return results, mark_score

    def _best_scan_candidate(self, gray, ordered_poly):
        """
        Test all rotations and both camera modes.

        Some Android/front-camera workflows save a mirrored image. A mirrored
        form still has valid corner markers, but its bubbles land at W-x, so
        reading only the normal grid undercounts partially answered sheets.
        """
        best = None
        for shift in range(4):
            candidate_poly = np.roll(ordered_poly, -shift, axis=0)
            warped = self._four_point_transform(gray, candidate_poly)

            for mirrored in (False, True):
                form_score = self._survey_form_score(warped, mirrored=mirrored)
                if form_score <= 0:
                    continue

                results, mark_score = self._read_results(
                    warped,
                    mirrored=mirrored,
                )
                answered = sum(1 for v in results.values() if v > 0)
                key = (form_score, mark_score, answered)

                if best is None or key > best["key"]:
                    best = {
                        "key": key,
                        "results": results,
                        "answered": answered,
                        "mirrored": mirrored,
                        "shift": shift,
                    }

        return best

    def _read_bubble(self, warped_gray, cy, cx):
        r = self.BUBBLE_RADIUS
        y1 = max(0, cy - r)
        y2 = min(warped_gray.shape[0], cy + r)
        x1 = max(0, cx - r)
        x2 = min(warped_gray.shape[1], cx + r)
        roi = warped_gray[y1:y2, x1:x2]
        return int(np.sum(roi < 150))

    def _read_bubble_metrics(self, warped_gray, cy, cx):
        r = self.BUBBLE_RADIUS
        y1 = max(0, cy - r)
        y2 = min(warped_gray.shape[0], cy + r)
        x1 = max(0, cx - r)
        x2 = min(warped_gray.shape[1], cx + r)
        roi = warped_gray[y1:y2, x1:x2].astype("float32")

        dark_pixels = int(np.sum(roi < 150))

        h, w = roi.shape
        yy, xx = np.ogrid[:h, :w]
        center_y = (h - 1) / 2.0
        center_x = (w - 1) / 2.0
        distance2 = (yy - center_y) ** 2 + (xx - center_x) ** 2
        inner = distance2 <= 7 ** 2
        ring = (distance2 >= 9 ** 2) & (distance2 <= 12 ** 2)

        if np.any(inner) and np.any(ring):
            contrast = float(roi[ring].mean() - roi[inner].mean())
        else:
            contrast = 0.0

        return {
            "dark_pixels": dark_pixels,
            "contrast": contrast,
        }

    def scan(self, path):
        """
        Process a survey image at `path`.

        Returns {1: choice, 2: choice, ..., 30: choice}, where choice is 1-5,
        or 0 if blank/unanswered. Returns None for unreadable or invalid forms.
        """
        self.last_error = ""
        img = cv2.imread(path)
        if img is None:
            self.last_error = "Cannot read this image file."
            print(f"[SurveyProcessor] {self.last_error}: {path}")
            return None

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        poly = self.find_survey_polygon(img)
        if poly is None:
            self.last_error = (
                "This does not look like the survey form. "
                "The four corner markers were not found."
            )
            print(f"[SurveyProcessor] REJECTED: {self.last_error}")
            return None

        best = self._best_scan_candidate(gray, poly)
        if best is None:
            self.last_error = (
                "This image does not match the survey form after correction."
            )
            print(
                f"[SurveyProcessor] REJECTED: {self.last_error}"
            )
            return None

        results = best["results"]
        answered = best["answered"]
        if answered < self.MIN_ANSWERED:
            self.last_error = (
                f"Only {answered} valid answers were detected. "
                "The form may be blank, too blurry, or shaded too lightly."
            )
            print(
                f"[SurveyProcessor] REJECTED: Only {answered} answers "
                f"detected (threshold: {self.MIN_ANSWERED}). "
                "Likely a blank or unrecognised form."
            )
            return None

        return results

    def _pick_choice(self, metrics):
        ranked = sorted(
            enumerate(metrics),
            key=lambda item: item[1]["dark_pixels"],
            reverse=True,
        )
        best_index, best = ranked[0]
        _, second = ranked[1]

        best_dark = best["dark_pixels"]
        second_dark = second["dark_pixels"]
        gap = best_dark - second_dark
        ratio = best_dark / max(second_dark, 1)

        if best_dark < self.MIN_MARK_PIXELS:
            return 0

        second_is_real_mark = (
            second_dark >= self.MIN_MARK_PIXELS
            and second["contrast"] >= self.MIN_MARK_CONTRAST
        )
        if second_is_real_mark:
            return 0

        if gap >= self.MIN_MARK_GAP and ratio >= self.MIN_MARK_RATIO:
            return best_index + 1

        # Blank rows and rows with multiple shaded answers are not tallied.
        return 0
