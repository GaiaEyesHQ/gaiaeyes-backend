#!/usr/bin/env bash
# Run only from the private upload directory. Overwrite exactly the approved pair.
set -euo pipefail
umask 077
: "${SG_TARGET_PATH_PROD:?Existing production destination is required}"
: "${RELEASE_ID:?Release identity is required}"
: "${PHP_SHA256:?Reviewed PHP checksum is required}"
: "${JS_SHA256:?Reviewed JavaScript checksum is required}"
case "$RELEASE_ID" in ''|*[!0-9-]*) echo 'Invalid release identity'; exit 1;; esac
case "$PHP_SHA256:$JS_SHA256" in *[!a-f0-9:]*) echo 'Invalid checksums'; exit 1;; esac
[[ ${#PHP_SHA256} == 64 && ${#JS_SHA256} == 64 ]] || { echo 'Invalid checksum length'; exit 1; }
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target_root=${SG_TARGET_PATH_PROD%/}
[[ "$target_root" = /* && "${target_root##*/}" = wp-content ]] || { echo 'Invalid production destination'; exit 1; }
target="$target_root/mu-plugins"
[[ -d "$target_root" && ! -L "$target_root" && -d "$target" && ! -L "$target" ]] || { echo 'Expected existing website directories'; exit 1; }
[[ "$source_dir" != "$target" && "$source_dir" != "$target_root"/* ]] || { echo 'Upload directory must be outside the website'; exit 1; }
files=(gaia-dashboard.php gaia-dashboard.js)
for file in "${files[@]}"; do
  [[ -f "$source_dir/$file" && ! -L "$source_dir/$file" ]] || { echo "Invalid uploaded file: $file"; exit 1; }
  [[ -f "$target/$file" && ! -L "$target/$file" ]] || { echo "Expected existing regular file: $file"; exit 1; }
  [[ ! -e "$target/.$file.$RELEASE_ID" && ! -L "$target/.$file.$RELEASE_ID" ]] || { echo 'Staging file already exists'; exit 1; }
done
verify_checksums() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum -c -; else shasum -a 256 -c -; fi
}
(cd "$source_dir"; printf '%s  gaia-dashboard.php\n%s  gaia-dashboard.js\n' "$PHP_SHA256" "$JS_SHA256" | verify_checksums)
php -l "$source_dir/gaia-dashboard.php"
mkdir "$source_dir/backups"
lock="$target/.gaia-dashboard-pair.lock"
mkdir "$lock" || { echo 'Another paired deployment holds the lock'; exit 1; }
replacing=0
committed=0
cleanup() {
  result=$?
  trap - EXIT
  if [[ $result != 0 && $replacing == 1 && $committed == 0 ]]; then
    for file in "${files[@]}"; do
      if cmp -s "$target/$file" "$source_dir/$file"; then
        cp -p "$source_dir/backups/$file" "$target/.$file.$RELEASE_ID"
        mv -f "$target/.$file.$RELEASE_ID" "$target/$file"
      elif ! cmp -s "$target/$file" "$source_dir/backups/$file"; then
        echo "Concurrent change detected in $file; preserved it for review"
      fi
    done
    echo 'Deployment did not complete; inspect pair and retained backups before retrying'
  fi
  for file in "${files[@]}"; do rm -f "$target/.$file.$RELEASE_ID"; done
  rmdir "$lock"
  exit "$result"
}
trap cleanup EXIT
for file in "${files[@]}"; do
  cp -p "$target/$file" "$source_dir/backups/$file"
  cp -p "$target/$file" "$target/.$file.$RELEASE_ID"
  cat "$source_dir/$file" > "$target/.$file.$RELEASE_ID"
done
# Detect a change since the snapshots before replacing either file.
for file in "${files[@]}"; do cmp -s "$target/$file" "$source_dir/backups/$file"; done
replacing=1
# Existing JavaScript works with the additive PHP proxy; install PHP first.
for file in "${files[@]}"; do
  cmp -s "$target/$file" "$source_dir/backups/$file"
  mv -f "$target/.$file.$RELEASE_ID" "$target/$file"
done
for file in "${files[@]}"; do cmp -s "$target/$file" "$source_dir/$file"; done
committed=1
printf 'installed_php_sha256=%s\ninstalled_js_sha256=%s\n' "$PHP_SHA256" "$JS_SHA256"
cache_status=unavailable
if command -v wp >/dev/null 2>&1; then
  if wp --path="$target_root/.." cache flush >/dev/null 2>&1 && wp --path="$target_root/.." sg cache purge >/dev/null 2>&1; then
    cache_status=cleared
  else
    cache_status=needs_review
  fi
fi
printf 'deployment=complete\nrelease_id=%s\ncache_status=%s\nbackups=private_upload_directory/backups\n' "$RELEASE_ID" "$cache_status"
