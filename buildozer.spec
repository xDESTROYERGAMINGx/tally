[app]

title = SnapStat
package.name = snapstat
package.domain = org.snapstat

source.dir = .
source.include_exts = py,png,jpg,jpeg,jfif,bmp,webp,tif,tiff,kv,db
source.exclude_dirs = .git,__pycache__,bin,.buildozer
source.exclude_patterns = *.pyc,*.pyo

version = 0.1.0

requirements = python3,kivy==2.3.1,kivymd==1.2.0,numpy,opencv,pyjnius

orientation = portrait
fullscreen = 0

android.permissions = CAMERA,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES
android.api = 35
android.minapi = 23
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True

android.allow_backup = True
android.logcat_filters = *:S python:D

[buildozer]

log_level = 2
warn_on_root = 1
