export DOCKER_USERNAME ?= fybrik
export DOCKER_PASSWORD ?= 
export DOCKER_HOSTNAME ?= ghcr.io
export DOCKER_NAMESPACE ?= fybrik
export DOCKER_TAGNAME ?= 0.0.1

DOCKER_IMG_NAME ?= fhir-read-module
DOCKER_FILE ?= ./Dockerfile
APP_IMG ?=  ${DOCKER_HOSTNAME}/${DOCKER_NAMESPACE}/${DOCKER_IMG_NAME}:${DOCKER_TAGNAME}
DOCKER_IMG_CONTEXT ?= .

.PHONY: docker-login
	docker login --username ${DOCKER_USERNAME} --password ${DOCKER_PASSWORD} ${DOCKER_HOSTNAME}

.PHONY: docker-all
	docker-all: docker-build docker-push

.PHONY: docker-build
docker-build:
ifneq (${DOCKER_PASSWORD},)
	docker login \
                --username ${DOCKER_USERNAME} \
                --password ${DOCKER_PASSWORD} ${DOCKER_HOSTNAME}
endif
	docker build ${DOCKER_IMG_CONTEXT} -t ${APP_IMG} -f ${DOCKER_FILE} --no-cache

.PHONY: docker-push
docker-push:
	docker push ${APP_IMG}

.PHONY: docker-rmi
docker-rmi:
	docker rmi ${APP_IMG} || true

