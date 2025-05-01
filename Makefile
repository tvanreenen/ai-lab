.PHONY: init

init:
	uv venv
	uv sync
#	uv run ipython kernel install --user --env VIRTUAL_ENV=$(pwd)/.venv --name=ai-lab

#lab:
#	uv run --with jupyter jupyter lab

#lab-headless:
#	uv run --with jupyter jupyter lab --no-browser


