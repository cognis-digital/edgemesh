# edgemesh gateway — tiny, stdlib-only image. No model weights live here;
# edgemesh meshes backends, so this stays small and runs anywhere.
FROM python:3.12-slim

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

# The gateway / cluster coordinator port.
EXPOSE 8780

# Bind to all interfaces inside the container so other nodes can reach it.
ENV EDGEMESH_HOST=0.0.0.0
ENTRYPOINT ["edgemesh"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8780"]
