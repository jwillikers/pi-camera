default: run

alias f := format
alias fmt := format

format:
    venv/bin/ruff format .
    just --fmt --unstable

hdr device="/dev/v4l-subdev2" action="enable":
    systemctl --user stop pi-camera.service || true
    pkill pi-camera || true
    v4l2-ctl --set-ctrl wide_dynamic_range={{ if action == "enable" { "1" } else { "0" } }} --device {{ device }}
    systemctl --user start pi-camera.service || true

init:
    #!/usr/bin/env bash
    set -euxo pipefail
    cat boot/firmware/config.txt.append | sudo tee --append /boot/firmware/config.txt
    ln --force --relative --symbolic wayfire.ini "{{ config_directory() }}/wayfire.ini"
    distro=$(awk -F= '$1=="ID" { print $2 ;}' /etc/os-release)
    if [ "$distro" = "debian" ]; then
        sudo apt-get --yes install firewalld python3-dev python3-picamera2 python3-venv raspberrypi-ui-mods wlr-randr
    fi
    [ -d venv ] || python -m venv --system-site-packages venv
    venv/bin/python -m pip install --requirement requirements.txt

init-dev: && sync
    #!/usr/bin/env bash
    set -euxo pipefail
    distro=$(awk -F= '$1=="ID" { print $2 ;}' /etc/os-release)
    if [ "$distro" = "debian" ]; then
        sudo apt-get --yes install python3-dev python3-picamera2 python3-venv
    fi
    [ -d venv ] || python -m venv --system-site-packages venv
    venv/bin/python -m pip install --requirement requirements-dev.txt
    venv/bin/pre-commit install

install: init
    mkdir --parents "{{ config_directory() }}/systemd/user"
    ln --force --relative --symbolic systemd/user/* "{{ config_directory() }}/systemd/user/"
    systemctl --user daemon-reload
    systemctl --user enable --now pi-camera.service

alias l := lint

lint:
    venv/bin/yamllint .
    venv/bin/ruff check --fix .

alias r := run

run output=(home_directory() / "Pictures"):
    venv/bin/python camera.py --output {{ output }}

sync:
    venv/bin/pip-sync requirements-dev.txt requirements.txt

alias t := test

test:
    venv/bin/pytest

alias u := update
alias up := update

update:
    venv/bin/pip-compile \
        --allow-unsafe \
        --generate-hashes \
        --reuse-hashes \
        --upgrade \
        requirements-dev.in
    venv/bin/pip-compile \
        --allow-unsafe \
        --generate-hashes \
        --reuse-hashes \
        --upgrade \
        requirements.in
    venv/bin/pre-commit autoupdate
