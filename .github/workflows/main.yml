# SnapStat Android Build

This project is configured for Buildozer.

## Build on Linux or WSL

Buildozer does not build Android APKs directly from native Windows. Use Ubuntu,
WSL, or a Linux VM.

```bash
cd /mnt/c/Users/User/Documents/Tally
python3 -m pip install --user buildozer cython
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev
buildozer android debug
```

The APK will be created under:

```text
bin/
```

Install on a connected phone:

```bash
buildozer android deploy run logcat
```

## Notes

- Camera and flash need the Android `CAMERA` permission.
- The app is locked to portrait in both `buildozer.spec` and `main.py`.
- The first build can take a long time because Android SDK/NDK and recipes are downloaded.

## Build Without Installing Linux Locally

This project includes a free GitHub Actions APK builder:

```text
.github/workflows/android-apk.yml
```

Use it like this:

1. Upload or push this project to a GitHub repository.
2. Open the repository on GitHub.
3. Go to **Actions**.
4. Select **Build Android APK**.
5. Press **Run workflow**.
6. Wait for the build to finish.
7. Open the finished workflow run and download **SnapStat-debug-apk** from
   **Artifacts**.

That downloaded artifact contains the installable debug APK for your phone.
