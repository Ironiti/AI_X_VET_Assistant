.PHONY: requirements create_environment test_environment detect_platform

################################################################################
# GLOBALS                                                                      #
################################################################################

PROJECT_NAME=AI VET Assistant
PYTHON_BIN?=python3.10

# 1. Platform‑specific variables
ifeq ($(OS),Windows_NT)                     # Windows
PYTHON_INTERPRETER=venv/Scripts/python.exe
PROJECT_DIR=$(CURDIR)
REQUIREMENTS_FILE=requirements-windows.txt
CUDA_PRESENT=$(shell where nvcc >nul 2>&1 && echo yes || echo no)          # nvcc check
else                                       # Unix (macOS / Linux)
UNAME_S:=$(shell uname -s)
PYTHON_INTERPRETER=$(shell pwd)/venv/bin/python3
PROJECT_DIR:=$(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))
REQUIREMENTS_FILE=requirements-unix.txt
ifeq ($(UNAME_S),Darwin)                   # macOS (no CUDA)
CUDA_PRESENT=no
else                                       # Linux
CUDA_PRESENT=$(shell command -v nvcc >/dev/null 2>&1 && echo yes || echo no)
endif
endif

# 2. PyTorch index selector
PYTORCH_CUDA_VERSION?=cu118                # default CUDA 11.8
ifeq ($(OS),Windows_NT)
TORCH_INDEX:=$(if $(filter yes,$(CUDA_PRESENT)),$(PYTORCH_CUDA_VERSION),cpu)
else
ifeq ($(UNAME_S),Darwin)
TORCH_INDEX:=metal
else
TORCH_INDEX:=$(if $(filter yes,$(CUDA_PRESENT)),$(PYTORCH_CUDA_VERSION),cpu)
endif
endif

# 3. Conda availability
HAS_CONDA:=$(shell conda --version >/dev/null 2>&1 && echo True || echo False)

# 4. kernel name: lowercase, underscores instead of spaces (for .ipynb files)
KERNEL_NAME=$(shell echo $(PROJECT_NAME) | tr '[:upper:]' '[:lower:]' | tr ' ' '_')

################################################################################
# COMMANDS                                                                     #
################################################################################

## Show detected configuration
detect_platform:
	@echo "Project name: $(PROJECT_NAME)"
	@echo "OS:           $(OS) $(UNAME_S)"
	@echo "Interpreter:  $(PYTHON_INTERPRETER)"
	@echo "CUDA present: $(CUDA_PRESENT)"
	@echo "Torch index:  $(TORCH_INDEX)"
	@echo "Has conda:    $(HAS_CONDA)"
	@echo "Req file:     $(REQUIREMENTS_FILE)"
	@echo "Kernel name:  $(KERNEL_NAME)"

## Create venv and upgrade basic tools
# create_environment:
# 	@command -v python3 >/dev/null 2>&1 || (echo "Python3 not found!" && exit 1)
# 	python3 -m venv venv && $(PYTHON_INTERPRETER) -m pip install -U pip setuptools wheel

create_environment:
	@command -v $(PYTHON_BIN) >/dev/null 2>&1 || (echo "$(PYTHON_BIN) not found!" && exit 1)
	$(PYTHON_BIN) -m venv venv && $(PYTHON_INTERPRETER) -m pip install -U pip setuptools wheel

## Run sanity‑check script
test_environment:
	$(PYTHON_INTERPRETER) utils/test_environment.py

## Install project requirements and matching PyTorch build
requirements: test_environment
	$(PYTHON_INTERPRETER) -m pip install -U pip setuptools wheel
	$(PYTHON_INTERPRETER) -m pip install -r $(REQUIREMENTS_FILE)
	@echo "Installing PyTorch from index '$(TORCH_INDEX)'..."
	$(PYTHON_INTERPRETER) -m pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/$(TORCH_INDEX)

# ## Register current virtual environment as a Jupyter kernel (local venv)
# add_kernel:
# 	$(PYTHON_INTERPRETER) -m ipykernel install --name=$(KERNEL_NAME) --display-name="Python (venv: $(PROJECT_NAME))" --prefix=$(PROJECT_DIR)/.jupyter_kernel

## Register current virtual environment as a Jupyter kernel (global)
add_kernel:
	$(PYTHON_INTERPRETER) -m ipykernel install --user --name=$(KERNEL_NAME) --display-name="Python (venv: $(PROJECT_NAME))"

# ## Remove registered Jupyter kernel for this project (local venv)
# remove_kernel:
# 	rm -rf $(PROJECT_DIR)/.jupyter_kernel/share/jupyter/kernels/$(KERNEL_NAME)

## Remove registered Jupyter kernel for this project (global)
remove_kernel:
	jupyter kernelspec uninstall -f $(KERNEL_NAME)

## Delete all compiled Python files
clean_py:
	find . -type f -name "*.py[co]" -delete
	find . -type d -name "__pycache__" -delete

## Lint using flake8
lint:
	flake8 src

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "$$(tput bold)Available rules:$$(tput sgr0)"
	@echo
	@sed -n -e "/^## / { \
		h; \
		s/.*//; \
		:doc" \
		-e "H; \
		n; \
		s/^## //; \
		t doc" \
		-e "s/:.*//; \
		G; \
		s/\\n## /---/; \
		s/\\n/ /g; \
		p; \
	}" ${MAKEFILE_LIST} \
	| LC_ALL='C' sort --ignore-case \
	| awk -F '---' \
		-v ncol=$$(tput cols) \
		-v indent=19 \
		-v col_on="$$(tput setaf 6)" \
		-v col_off="$$(tput sgr0)" \
	'{ \
		printf "%s%*s%s ", col_on, -indent, $$1, col_off; \
		n = split($$2, words, " "); \
		line_length = ncol - indent; \
		for (i = 1; i <= n; i++) { \
			line_length -= length(words[i]) + 1; \
			if (line_length <= 0) { \
				line_length = ncol - indent - length(words[i]) - 1; \
				printf "\n%*s ", -indent, " "; \
			} \
			printf "%s ", words[i]; \
		} \
		printf "\n"; \
	}' \
	| more $(shell test $(shell uname) = Darwin && echo '--no-init --raw-control-chars')
