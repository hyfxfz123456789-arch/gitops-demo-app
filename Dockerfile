FROM 192.168.119.166:8443/gitops-demo/python-base:3.13.18-alpine

ARG APP_VERSION=dev
ARG GIT_COMMIT=unknown
ENV APP_VERSION=${APP_VERSION} GIT_COMMIT=${GIT_COMMIT} PORT=8080

WORKDIR /app
COPY app.py /app/app.py

# 运行时只使用 Python 标准库，不需要 pip 和 ensurepip。
RUN python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.13/ensurepip

USER 10001:10001
EXPOSE 8080
CMD ["python", "/app/app.py"]
