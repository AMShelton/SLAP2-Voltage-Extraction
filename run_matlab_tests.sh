#!/usr/bin/env bash

run_matlab_tests() {
    local repo_url="https://github.com/AllenNeuralDynamics/SLAP2-Voltage-Extraction.git"
    local branch="python_translation"
    local repo_dir script_dir matlab_status

    # When pasted, prefer the repository containing the current directory.
    # When executed as a file, also check the directory containing this script.
    if repo_dir="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null)"; then
        echo "Using current repository: $repo_dir"
    else
        script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
        if repo_dir="$(git -C "$script_dir" rev-parse --show-toplevel 2>/dev/null)"; then
            echo "Using repository containing this script: $repo_dir"
        else
            repo_dir="$HOME/SLAP2-Voltage-Extraction"
            if [[ -d "$repo_dir/.git" ]]; then
                echo "Using existing repository: $repo_dir"
            elif [[ -e "$repo_dir" ]]; then
                echo "Cannot clone: $repo_dir exists but is not a Git repository." >&2
                return 2
            else
                git clone --branch "$branch" --single-branch \
                    "$repo_url" "$repo_dir" || return $?
            fi
        fi
    fi

    if ! git -C "$repo_dir" remote get-url origin >/dev/null 2>&1; then
        git -C "$repo_dir" remote add origin "$repo_url" || return $?
    fi

    git -C "$repo_dir" fetch origin "$branch" || return $?
    git -C "$repo_dir" switch "$branch" || return $?
    git -C "$repo_dir" merge --ff-only "origin/$branch" || return $?

    cd "$repo_dir" || return $?
    matlab -batch "fprintf('MATLAB version: %s\n', version); fprintf('MATLAB release: %s\n', version('-release')); fprintf('Architecture: %s\n', computer('arch')); disp('Installed products:'); ver; clear classes; setup; results = runtests('tests'); disp(table(results)); assertSuccess(results)"
    matlab_status=$?
    echo "MATLAB finished with exit code $matlab_status"
    return "$matlab_status"
}

run_matlab_tests
