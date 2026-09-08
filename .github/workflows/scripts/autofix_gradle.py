#!/usr/bin/env python3
"""
Auto-fix untuk project Flutter/Android yang di-upload user, sebelum di-build.
Tujuan: benerin kesalahan syntax/konfigurasi UMUM yang sering muncul di ZIP
project orang lain, TANPA mengubah logic aplikasi mereka.

Dipanggil: python3 autofix_gradle.py <path_ke_folder_project_flutter>

Yang dibenerin:
1. build.gradle.kts pakai syntax Groovy tanpa '=' (compileSdk 35, targetSdk 35,
   minSdk 21, dst) -> ditambahin '=' karena Kotlin DSL wajib pakai '='.
2. compileSdk / targetSdk yang di bawah 34 -> dinaikin ke 34 (banyak plugin
   Flutter modern minimal butuh compileSdk 34+, di bawah itu sering gagal
   manifest merger / dependency resolution).
3. ndkVersion yang di-hardcode ke versi tertentu -> diarahkan ke
   flutter.ndkVersion (versi yang udah dibundel Flutter SDK), biar gak perlu
   download NDK terpisah yang beda versi (lebih cepat & lebih konsisten).
4. AGP (Android Gradle Plugin) yang di bawah 8.1.0 -> dinaikin ke 8.1.0,
   supaya kompatibel sama compileSdk 34/35.
5. Gradle wrapper yang di bawah 8.4 -> dinaikin ke gradle-8.4-all.zip.

Semua perubahan di-log ke stdout supaya kelihatan di log GitHub Actions,
gampang di-audit kalau ada yang aneh.
"""
import os
import re
import sys

if len(sys.argv) < 2:
    print("Usage: autofix_gradle.py <project_dir>")
    sys.exit(1)

PROJECT_DIR = sys.argv[1]
changes = []


def find_file(*candidates):
    for c in candidates:
        p = os.path.join(PROJECT_DIR, c)
        if os.path.isfile(p):
            return p
    return None


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ── 1 & 2 & 3: android/app/build.gradle(.kts) ────────────────────────────
app_gradle = find_file("android/app/build.gradle.kts", "android/app/build.gradle")
if app_gradle:
    is_kts = app_gradle.endswith(".kts")
    src = read(app_gradle)
    original = src

    if is_kts:
        # Fix: properti Kotlin DSL yang ditulis tanpa '=' (gaya Groovy)
        # contoh: "    compileSdk 35"  ->  "    compileSdk = 35"
        int_props = ["compileSdk", "targetSdk", "minSdk", "versionCode"]
        for prop in int_props:
            pattern = re.compile(rf"^(\s*){prop}\s+(\d+)\s*$", re.MULTILINE)
            new_src, n = pattern.subn(rf"\1{prop} = \2", src)
            if n:
                changes.append(f"[app build.gradle.kts] '{prop} <angka>' -> '{prop} = <angka>' ({n}x)")
                src = new_src

        str_props = ["versionName", "applicationId", "namespace", "ndkVersion"]
        for prop in str_props:
            pattern = re.compile(rf'^(\s*){prop}\s+("[^"]*")\s*$', re.MULTILINE)
            new_src, n = pattern.subn(rf"\1{prop} = \2", src)
            if n:
                changes.append(f"[app build.gradle.kts] '{prop} \"...\"' -> '{prop} = \"...\"' ({n}x)")
                src = new_src

        # compileSdkVersion 35 (gaya lama) -> compileSdkVersion(35) untuk .kts
        for prop in ["compileSdkVersion", "minSdkVersion", "targetSdkVersion"]:
            pattern = re.compile(rf"^(\s*){prop}\s+(\d+)\s*$", re.MULTILINE)
            new_src, n = pattern.subn(rf"\1{prop}(\2)", src)
            if n:
                changes.append(f"[app build.gradle.kts] '{prop} <angka>' -> '{prop}(<angka>)' ({n}x)")
                src = new_src

    # ── Naikkan compileSdk / targetSdk kalau di bawah 34 ─────────────────
    def bump_sdk(match, prop_name):
        val = int(match.group(2))
        if val < 34:
            changes.append(f"[app build.gradle{'.kts' if is_kts else ''}] {prop_name} {val} -> 34 (terlalu lama, dinaikkan biar kompatibel plugin modern)")
            return f"{match.group(1)}{prop_name}{' = ' if is_kts else ' '}34"
        return match.group(0)

    for prop in ["compileSdk", "targetSdk"]:
        eq = r"\s*=\s*" if is_kts else r"\s+"
        pattern = re.compile(rf"^(\s*){prop}{eq}(\d+)\s*$", re.MULTILINE)
        src = pattern.sub(lambda m, p=prop: bump_sdk(m, p), src)

    # Gaya lama: compileSdkVersion 33 / targetSdkVersion 33 (groovy) atau
    # compileSdkVersion(33) (kts, setelah fix di atas)
    for prop in ["compileSdkVersion", "targetSdkVersion"]:
        if is_kts:
            pattern = re.compile(rf"^(\s*){prop}\((\d+)\)\s*$", re.MULTILINE)
            def bump_kts(m, p=prop):
                val = int(m.group(2))
                if val < 34:
                    changes.append(f"[app build.gradle.kts] {p}({val}) -> {p}(34)")
                    return f"{m.group(1)}{p}(34)"
                return m.group(0)
            src = pattern.sub(bump_kts, src)
        else:
            pattern = re.compile(rf"^(\s*){prop}\s+(\d+)\s*$", re.MULTILINE)
            def bump_groovy(m, p=prop):
                val = int(m.group(2))
                if val < 34:
                    changes.append(f"[app build.gradle] {p} {val} -> {p} 34")
                    return f"{m.group(1)}{p} 34"
                return m.group(0)
            src = pattern.sub(bump_groovy, src)

    # ── Arahkan ndkVersion ke bawaan Flutter (hindari download NDK asing) ─
    if is_kts:
        ndk_pattern = re.compile(r'^(\s*)ndkVersion\s*=\s*"[^"]*"\s*$', re.MULTILINE)
        new_src, n = ndk_pattern.subn(r"\1ndkVersion = flutter.ndkVersion", src)
    else:
        ndk_pattern = re.compile(r'^(\s*)ndkVersion\s+"[^"]*"\s*$', re.MULTILINE)
        new_src, n = ndk_pattern.subn(r"\1ndkVersion flutter.ndkVersion", src)
    if n:
        changes.append(f"[app build.gradle{'.kts' if is_kts else ''}] ndkVersion di-hardcode -> pakai flutter.ndkVersion ({n}x)")
        src = new_src

    if src != original:
        write(app_gradle, src)
else:
    print("⚠️  android/app/build.gradle(.kts) tidak ditemukan — skip auto-fix app gradle.")

# ── 4: AGP version di root android/build.gradle(.kts) ────────────────────
root_gradle = find_file("android/build.gradle.kts", "android/build.gradle")
if root_gradle:
    is_kts = root_gradle.endswith(".kts")
    src = read(root_gradle)
    original = src

    # gaya classpath lama: classpath 'com.android.tools.build:gradle:X.X.X'
    def bump_agp_classpath(m):
        ver = m.group(2)
        major_minor = tuple(int(x) for x in ver.split(".")[:2])
        if major_minor < (8, 1):
            changes.append(f"[root build.gradle] AGP classpath {ver} -> 8.1.0 (terlalu lama untuk compileSdk 34/35)")
            return f"{m.group(1)}8.1.0{m.group(3)}"
        return m.group(0)

    pattern = re.compile(r"(['\"]com\.android\.tools\.build:gradle:)([\d.]+)(['\"])")
    src = pattern.sub(bump_agp_classpath, src)

    # gaya plugin baru: id("com.android.application") version "X.X.X"
    def bump_agp_plugin(m):
        ver = m.group(2)
        major_minor = tuple(int(x) for x in ver.split(".")[:2])
        if major_minor < (8, 1):
            changes.append(f"[root build.gradle{'.kts' if is_kts else ''}] AGP plugin version {ver} -> 8.1.0")
            return f'{m.group(1)}8.1.0"'
        return m.group(0)

    pattern2 = re.compile(r'(id\("com\.android\.application"\)\s+version\s+")([\d.]+)(")')
    src = pattern2.sub(bump_agp_plugin, src)

    if src != original:
        write(root_gradle, src)

# ── 5: Gradle wrapper version ─────────────────────────────────────────────
wrapper_props = find_file("android/gradle/wrapper/gradle-wrapper.properties")
if wrapper_props:
    src = read(wrapper_props)
    original = src

    def bump_wrapper(m):
        ver = m.group(1)
        parts = tuple(int(x) for x in re.split(r"[.\-]", ver)[:2])
        if parts < (8, 4):
            changes.append(f"[gradle-wrapper.properties] Gradle {ver} -> 8.4 (kurang dari minimum buat AGP 8.1)")
            return "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.4-all.zip"
        return m.group(0)

    pattern = re.compile(r"distributionUrl=.*gradle-([\d.]+)-\w+\.zip")
    src = pattern.sub(bump_wrapper, src)

    if src != original:
        write(wrapper_props, src)

# ── Ringkasan ──────────────────────────────────────────────────────────────
if changes:
    print("🔧 Auto-fix diterapkan:")
    for c in changes:
        print(f"   - {c}")
else:
    print("✅ Tidak ada masalah konfigurasi umum yang terdeteksi, project dipakai apa adanya.")
