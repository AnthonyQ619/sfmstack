#!/usr/bin/env bash
# Build every base and every module image, in dependency order.
#
#   tools/build_images.sh              everything
#   tools/build_images.sh runtime      only bases whose name matches
#   tools/build_images.sh track_       only modules whose directory matches
#
# Run from the repository root; the build context is the root in every case.
#
# Why a script rather than a note in the README: sfmkit is COPYed into
# `sfmstack/runtime`, which is the first layer of every other image, so any change
# to the package invalidates all of them at once. That is the correct behaviour --
# a module running last week's sfmkit against this week's artifacts is exactly the
# skew containers exist to prevent -- but it means "rebuild the one image I
# touched" is usually wrong, and the order below is not optional.
#
# The cost of that layout, learned the hard way: because sfmkit sits UNDER the
# dependency installs, a one-line change to the contract layer forces every base
# above it to re-resolve its dependencies from the network. In August 2026 that
# turned a docstring edit into a failed build, when the cu124 index had been pruned
# of a wheel torch 2.6.0 hard-pins. The cached layer had been hiding it for months.
# Two consequences worth remembering: a green build here is not evidence the images
# are REPRODUCIBLE, only that they are current; and putting the contract layer on
# TOP of the dependency layers instead of under them would make an sfmkit change
# cost a 2 MB rebuild instead of a 10 GB one.

set -euo pipefail
cd "$(dirname "$0")/.."

FILTER="${1:-}"
match() { [[ -z "$FILTER" || "$1" == *"$FILTER"* ]]; }

build() {  # build <tag> <dockerfile>
  local tag="$1" file="$2"
  printf '%-34s ' "$tag"
  if docker build -q -t "$tag" -f "$file" . > /tmp/sfmbuild.$$ 2>&1; then
    echo "ok   $(docker images --format '{{.Size}}' "$tag" | head -1)"
  else
    echo "FAILED"; tail -25 /tmp/sfmbuild.$$; rm -f /tmp/sfmbuild.$$; exit 1
  fi
  rm -f /tmp/sfmbuild.$$
}

# Bases, in dependency order. runtime first: everything else is FROM it, directly
# or through runtime-torch.
BASES=(
  "sfmstack/runtime:1.0                docker/runtime/Dockerfile"
  "sfmstack/runtime-torch:1.0          docker/runtime-torch/Dockerfile"
  "sfmstack/runtime-lightglue:1.0      docker/runtime-lightglue/Dockerfile"
  "sfmstack/runtime-kornia:1.0         docker/runtime-kornia/Dockerfile"
  "sfmstack/runtime-superglue:1.0      docker/runtime-superglue/Dockerfile"
  "sfmstack/runtime-roma:1.0           docker/runtime-roma/Dockerfile"
  "sfmstack/runtime-roma-fused:1.0     docker/runtime-roma-fused/Dockerfile"
  "sfmstack/runtime-vggt:1.0           docker/runtime-vggt/Dockerfile"
  "sfmstack/runtime-mapanything:1.0    docker/runtime-mapanything/Dockerfile"
)

for entry in "${BASES[@]}"; do
  read -r tag file <<< "$entry"
  match "$tag" && build "$tag" "$file"
done

# Modules: the tag comes out of the manifest, so a renamed image cannot drift
# from what the registry will look for.
for dir in modules/*/; do
  name="$(basename "$dir")"
  match "$name" || continue
  [[ -f "$dir/Dockerfile" ]] || continue
  tag="$(grep -m1 '^image:' "$dir/module.yaml" | awk '{print $2}')"
  build "$tag" "$dir/Dockerfile"
done
