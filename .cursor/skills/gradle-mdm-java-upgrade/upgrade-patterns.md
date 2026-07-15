# Build.gradle Transform Catalogue (Gradle 6 → 7)

Reference for the transforms applied by `apply_build_gradle_changes()` in the migration scripts.
Each entry shows: the problem, the sed pattern, and why it is needed.

---

## 1. Insecure protocol flag

**Problem:** Gradle 7 rejects HTTP maven repos without explicit opt-in.

```bash
sed -i 's|url = "${artifactory_plugin_url}"|&\n            allowInsecureProtocol = true|g' build.gradle
sed -i 's|url = "${artifactory_virtual_url}"|&\n            allowInsecureProtocol = true|g' build.gradle
```

**Also:** ensure both `artifactory_plugin_url` and `artifactory_virtual_url` blocks exist in `buildscript.repositories` (script adds the missing one).

---

## 2. Karaf plugin replacement

**Problem:** `com.github.lburgazzoli:gradle-karaf-plugin` is incompatible with Gradle 7; replaced by the internal `plugin-karaf:1.0.0`.

```bash
# If plugin-karaf already present, just remove the old line:
sed -i "/classpath .*com\.github\.lburgazzoli:gradle-karaf-plugin/d" build.gradle

# Otherwise replace the old line:
sed -i "s|classpath '.*com.github.lburgazzoli:gradle-karaf-plugin.*'|classpath 'com.nokia.nsp.mdm:plugin-karaf:1.0.0'|" build.gradle

# And replace the apply plugin reference:
sed -i "s/apply plugin: 'com.github.lburgazzoli.karaf'/apply plugin: 'nsp-mdm-karaf'/" build.gradle
```

---

## 3. Plugin version upgrades

| Old | New | Reason |
|---|---|---|
| `build-orbw-gradle-plugin:0.6.+` / `0.7.+` / `1.0.+` / `1.2.+` | `2.1.+` | Gradle 7 compatibility |
| `biz.aQute.bnd.gradle:3.5.+` | `6.4.0` | OSGi bundle support in Gradle 7 |
| `biz.aQute.bnd.gradle:4.*` | `6.4.0` | same |
| `plugin-mdm-adapter-development:1.0.+` / `1.1.+` / `2.0.+` | `3.0.+` | Gradle 7 adapter plugin |

```bash
sed -i 's/build-orbw-gradle-plugin:[01]\.[0-9.+]*/build-orbw-gradle-plugin:2.1.+/' build.gradle
sed -i 's/biz\.aQute\.bnd\.gradle:[34]\.[0-9.+]*/biz.aQute.bnd.gradle:6.4.0/' build.gradle
sed -i 's/plugin-mdm-adapter-development:[12]\.[01]\.+/plugin-mdm-adapter-development:3.0.+/' build.gradle
```

---

## 4. Removed plugins

```bash
sed -i "/apply plugin: *'findbugs'/d" build.gradle   # removed in Gradle 6+
sed -i "/apply plugin: *'maven'/d" build.gradle       # replaced by maven-publish
```

---

## 5. Dependency configuration renames

Gradle 7 removes deprecated configurations. Order matters (most-specific first):

| Old | New |
|---|---|
| `bundleCompile` | `implementation` |
| `testCompile` | `testImplementation` |
| `testRuntime` | `testRuntimeOnly` |
| `compile` | `implementation` |
| `runtime` | `runtimeOnly` |

```bash
sed -i 's/bundleCompile /implementation /g; s/bundleCompile(/implementation(/g' build.gradle
sed -i 's/testCompile /testImplementation /g; s/testCompile(/testImplementation(/g' build.gradle
sed -i 's/testRuntime /testRuntimeOnly /g; s/testRuntime(/testRuntimeOnly(/g' build.gradle
sed -i 's/\bcompile /implementation /g; s/\bcompile(/implementation(/g' build.gradle
sed -i 's/\bruntime /runtimeOnly /g; s/\bruntime(/runtimeOnly(/g' build.gradle
```

**Also update `configurations { }` extendsFrom targets:**
```bash
sed -i 's/compile\.extendsFrom bundleCompile/implementation.extendsFrom bundleCompile/' build.gradle
sed -i 's/compile\.extendsFrom embedded/implementation.extendsFrom embedded/' build.gradle
sed -i 's/runtime\.extendsFrom bundleRuntime/runtimeOnly.extendsFrom bundleRuntime/' build.gradle
```

---

## 6. Publishing block cleanup

```bash
# Remove "artifact jar" (redundant; from components.java covers it)
sed -i '/^[[:space:]]*artifact jar[[:space:]]*$/d' build.gradle
```

---

## 7. Java source/target compatibility block

If no `sourceCompatibility` exists, inject after the `publishing { }` closing braces:

```groovy
java {
    sourceCompatibility = JavaVersion.VERSION_1_8
    targetCompatibility = JavaVersion.VERSION_1_8
}
```

The script tries up to 4 patterns for 0–3 optional lines between `from components.java` and the three closing braces.

---

## 8. Jar classpath: compile → runtimeClasspath

```bash
sed -i 's/configurations\.compile/configurations.runtimeClasspath/g' build.gradle
sed -i 's/project\.configurations\.compile\.each/project.configurations.runtimeClasspath.each/g' build.gradle
```

---

## 9. Bnd manifest → bundle (conditional)

Only when `biz.aQute.bnd.builder` is applied (otherwise `bundle()` method does not exist):

```bash
if grep -q "biz.aQute.bnd.builder\|bnd.builder" build.gradle; then
  sed -i 's/manifest { attributes(/bundle { bnd(/' build.gradle
fi
```

---

## Template for a new migration cycle

Copy this block into the new `apply_build_gradle_changes()` and fill in the new patterns:

```bash
apply_build_gradle_changes_v<N>() {
  local f="build.gradle"
  [[ ! -f "$f" ]] && return 0

  # 1) <description of change>
  sed -i 's/<old>/<new>/g' "$f"

  # 2) ...
}
```

Key questions to answer for each new cycle:
- What Gradle version is the target? (changes plugin version constraints)
- What Java version is the target? (`JavaVersion.VERSION_1_8` → `VERSION_17` etc.)
- Are there new deprecated configurations or APIs to rename?
- Has the internal plugin set changed? (check BOM diff for `plugin-*` artifacts)
- Does the reference repo diff (`git diff <old> <new> build.gradle`) show anything not in the list above?
