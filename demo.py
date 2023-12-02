import modal, os, sys, shlex

stub = modal.Stub("jupyter")
volume = modal.NetworkFileSystem.new().persisted("jupyter")

@stub.function(
    image=modal.Image.from_registry("nvidia/cuda:11.8.0-devel-ubuntu22.04", add_python="3.10")
    .run_commands(
        "apt update -y && \
        apt install -y software-properties-common && \
        apt update -y && \
        add-apt-repository -y ppa:git-core/ppa && \
        add-apt-repository -y ppa:flexiondotorg/nvtop && \
        apt update -y && \
        apt install -y git git-lfs nvtop && \
        git --version  && \
        apt install -y aria2 libgl1 libglib2.0-0 wget && \
        wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && \
        dpkg -i cloudflared-linux-amd64.deb && \
        pip install -q torch==2.0.1+cu118 torchvision==0.15.2+cu118 torchaudio==2.0.2+cu118 torchtext==0.15.2 torchdata==0.6.1 --extra-index-url https://download.pytorch.org/whl/cu118 && \
        pip install -q xformers==0.0.20 triton==2.0.0 packaging==23.1 notebook"
    ),
    network_file_systems={"/content/jupyter": volume},
    gpu="A10G",
    timeout=60000,
)
async def run():
    import atexit, requests, subprocess, time, re
    from random import randint
    from threading import Timer
    from queue import Queue
    def cloudflared(port, metrics_port, output_queue):
        atexit.register(lambda p: p.terminate(), subprocess.Popen(['cloudflared', 'tunnel', '--url', f'http://127.0.0.1:{port}', '--metrics', f'127.0.0.1:{metrics_port}'], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        attempts, tunnel_url = 0, None
        while attempts < 10 and not tunnel_url:
            attempts += 1
            time.sleep(3)
            try:
                tunnel_url = re.search("(?P<url>https?:\/\/[^\s]+.trycloudflare.com)", requests.get(f'http://127.0.0.1:{metrics_port}/metrics').text).group("url")
            except:
                pass
        if not tunnel_url:
            raise Exception("Can't connect to Cloudflare Edge")
        output_queue.put(tunnel_url)
    output_queue, metrics_port = Queue(), randint(8100, 9000)
    thread = Timer(2, cloudflared, args=(7860, metrics_port, output_queue))
    thread.start()
    thread.join()
    tunnel_url = output_queue.get()
    os.environ['webui_url'] = tunnel_url
    print(tunnel_url)
    os.system(f"jupyter notebook --allow-root --port 7860 --ip 0.0.0.0 --NotebookApp.token '' --no-browse")

@stub.local_entrypoint()
def main():
    run.remote()