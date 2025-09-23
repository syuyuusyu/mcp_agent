APP_NAME = mcp-agent
IMAGE = $(APP_NAME):latest
PYTHON_VERSION = 3.11
CONFIG_DIR ?= $(PWD)
PORT ?= 8002

.PHONY: build run shell push clean

build:
	@echo "[BUILD] $(IMAGE)"
	docker build --build-arg PYTHON_VERSION=$(PYTHON_VERSION) -t $(IMAGE) .

run:
	@echo "[RUN] $(IMAGE) -> http://localhost:$(PORT)"
	docker run --rm -it -p $(PORT):8002 -e APP_PORT=8002 -v $(CONFIG_DIR):/app/config_ext $(IMAGE) --host 0.0.0.0 --port 8002

shell:
	@docker run --rm -it $(IMAGE) /bin/bash

clean:
	@docker rmi $(IMAGE) 2>/dev/null || true

# Example: make build push REG=your-registry.example.com
REG ?=

push: build
ifndef REG
	$(error Set REG=registry.example.com to push)
endif
	docker tag $(IMAGE) $(REG)/$(IMAGE)
	docker push $(REG)/$(IMAGE)
