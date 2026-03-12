ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and dependencies
RUN apk add --no-cache python3 py3-pip py3-aiohttp py3-aiofiles py3-yaml \
    && pip3 install --no-cache-dir --break-system-packages pychromecast

# Copy application
COPY app /app
COPY frontend /frontend
COPY run.sh /run.sh

RUN chmod a+x /run.sh

CMD ["/run.sh"]
