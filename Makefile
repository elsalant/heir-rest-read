export DOCKER_USERNAME ?= fybrik
export DOCKER_PASSWORD ?= 
export DOCKER_HOSTNAME ?= ghcr.io
export DOCKER_NAMESPACE ?= fybrik
export DOCKER_TAGNAME ?= 0.0.1

DOCKER_IMG_NAME ?= fhir-read-chart
DOCKER_FILE ?= ./python/Dockerfile
APP_IMG ?=  ${DOCKER_HOSTNAME}/${DOCKER_NAMESPACE}/${DOCKER_IMG_NAME}:${DOCKER_TAGNAME}
DOCKER_IMG_CONTEXT ?= .

CHART_NAME ?= charts/${DOCKER_IMG_NAME}
HELM_CHART_NAME ?= fhir-read-chart
CHART_REGISTRY_PATH := oci://${DOCKER_HOSTNAME}/${DOCKER_NAMESPACE}

HELM_RELEASE ?= rel1-${DOCKER_IMG_NAME}
HELM_TAG ?= 0.0.1
HELM_VALUES ?= \
	--set hello=world1

TEMP := /tmp

export HELM_EXPERIMENTAL_OCI=1
export GODEBUG=x509ignoreCN=0

.PHONY: helm-login
helm-login:
ifneq (${DOCKER_PASSWORD},)
	helm registry login -u "${DOCKER_USERNAME}" -p "${DOCKER_PASSWORD}" ${DOCKER_HOSTNAME}
endif

.PHONY: helm-verify
helm-verify:
	helm lint ${CHART_NAME}
	helm install --dry-run ${HELM_RELEASE} ${CHART_NAME} ${HELM_VALUES}

.PHONY: helm-uninstall
helm-uninstall:
	helm uninstall ${HELM_RELEASE} || true

.PHONY: helm-install
helm-install:
	helm install ${HELM_RELEASE} ${CHART_NAME} ${HELM_VALUES}

.PHONY: helm-package
helm-package:
	helm package ${CHART_NAME} --destination=${TEMP}

.PHONY: helm-push
helm-push: helm-login
	helm push ${TEMP}/${HELM_CHART_NAME}-${HELM_TAG}.tgz ${CHART_REGISTRY_PATH}
	rm -rf ${TEMP}/${HELM_CHART_NAME}-${HELM_TAG}.tgz

.PHONY: helm-chart-pull
helm-chart-pull: helm-login
	helm pull ${CHART_REGISTRY_PATH}/${CHART_NAME} --version ${HELM_TAG}

.PHONY: helm-chart-list
helm-chart-list:
	helm list

.PHONY: helm-chart-install
helm-chart-install:
	helm install ${HELM_RELEASE} ${CHART_REGISTRY_PATH}/${CHART_NAME} --version ${HELM_TAG} ${HELM_VALUES}
	helm list

.PHONY: helm-template
helm-template:
	helm template ${HELM_RELEASE} ${CHART_REGISTRY_PATH} --version ${HELM_TAG} ${HELM_VALUES}

.PHONY: helm-debug
helm-debug: helm
	helm template ${HELM_RELEASE} ${CHART_REGISTRY_PATH} ${HELM_VALUES} --version ${HELM_TAG} --debug

.PHONY: helm-actions
helm-actions:
	helm show values --version ${HELM_TAG} ${CHART_NAME} | yq -y -r .actions

.PHONY: helm-all
helm-all: helm-verify helm-chart-push helm-chart-pull helm-uninstall helm-chart-install
