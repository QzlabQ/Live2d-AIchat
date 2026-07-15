FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG ALL_PROXY
ARG http_proxy
ARG https_proxy
ARG all_proxy

ENV DEBIAN_FRONTEND=noninteractive
ENV CONDA_DIR=/opt/conda
ENV CONDA_ENV_NAME=ai-chat-gpu
ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV ALL_PROXY=${ALL_PROXY}
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}
ENV all_proxy=${all_proxy}
ENV PATH=/opt/conda/bin:/opt/conda/envs/ai-chat-gpu/bin:${PATH}
ENV PYTHONUNBUFFERED=1

RUN apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --fix-missing --no-install-recommends -o Acquire::Retries=5 \
    bash \
    build-essential \
    ca-certificates \
    curl \
    ffmpeg \
    git \
    libglib2.0-0 \
    libgomp1 \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-py311_24.5.0-0-Linux-x86_64.sh -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p "${CONDA_DIR}" \
    && rm -f /tmp/miniconda.sh

WORKDIR /app

COPY environment.container.yml /tmp/environment.container.yml
COPY requirements.runtime.txt requirements.postgres.txt requirements.asr.txt requirements.knowledge.txt requirements.tts.txt requirements.container.txt /tmp/

RUN conda env create -f /tmp/environment.container.yml \
    && /opt/conda/envs/${CONDA_ENV_NAME}/bin/python -m pip install --upgrade pip \
    && /opt/conda/envs/${CONDA_ENV_NAME}/bin/python -m pip install --no-build-isolation -r /tmp/requirements.container.txt \
    && conda clean -afy

COPY main.py /app/main.py
COPY app /app/app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
