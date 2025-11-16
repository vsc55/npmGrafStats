#!/usr/bin/env python3
""" Generte log type Nginx (combined + host) in background. """
import random
import time
import threading
from typing import List
from pathlib import Path


class NginxLogGenerator:
    """
    Generador de logs tipo Nginx (formato combinado + host) en background.

    Formato aproximado:
    $host $remote_addr - - [time_local] "METHOD URI HTTP/x.x" status size "ref" "ua"
    """
    debug: bool = False

    HOSTS = [
        "www.ejemplo.com",
        "tienda.ejemplo.com",
        "api.ejemplo.com",
        "static.ejemplo.com",
        "intranet.local",
        "admin.ejemplo.com",
        "blog.ejemplo.com",
        "foro.ejemplo.com",
        "media.ejemplo.com",
        "dev.ejemplo.com"
    ]

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Mozilla/5.0 (X11; Linux x86_64)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "curl/7.88.0",
        "Wget/1.21.3",
        "PostmanRuntime/7.39.0",
        "Googlebot/2.1 (+http://www.google.com/bot.html)",
        "Bingbot/2.0 (+http://www.bing.com/bingbot.htm)",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
        "Mozilla/5.0 (Android 11; Mobile; rv:89.0) Gecko/89.0 Firefox/89.0",
    ]

    REFERRERS = [
        "-",
        "https://www.google.com/",
        "https://www.bing.com/",
        "https://www.facebook.com/",
        "https://twitter.com/",
        "https://www.ejemplo.com/",
        "https://tienda.ejemplo.com/productos",
    ]

    PRIVATE_IP_RANGES = [
        ("10", "0", "0"),       # 10.0.0.0 – 10.255.255.255
        ("172", "16", "0"),     # 172.16.0.0 – 172.31.255.255
        ("192", "168", "0"),    # 192.168.0.0 – 192.168.255.255
    ]

    METHODS = {
        "GET": 70,
        "POST": 30,
        "HEAD": 10,
        "PUT": 5,
        "DELETE": 5,
        "PATCH": 5,
        "OPTIONS": 5,
    }
    HTTP_VERSIONS = ["HTTP/1.0", "HTTP/1.1", "HTTP/2.0"]

    STATUS_DISTRIBUTION = {
        200: {"weight": 70},
        301: {"weight": 5},
        302: {"weight": 5},
        304: {"weight": 5},
        400: {"weight": 2},
        401: {"weight": 1},
        403: {"weight": 1},
        404: {"weight": 8},
        499: {
            "weight": 2,
            "length_zero": True,    # Length 0
            "header_mode": "499",   # Special Header: - - 499 -
        },
        500: {"weight": 1},
        502: {"weight": 1},
    }


    _output: str = ""

    def __init__(self, output: str = "", debug: bool = False):
        self.debug = debug
        self.output = output
        self.base_interval = 1.0
        self.min_batch = 1
        self.max_batch = 5
        self.max_clients = 200

        self._running = False
        self._thread: threading.Thread | None = None
        self._client_ips: List[str] = []


    # ---------- Properties ----------

    @property
    def output(self) -> str:
        """Get or set the output file path."""
        base = Path(__file__).resolve().parent.parent.parent
        path = self._output.replace("{workdir}", str(base))
        return str(Path(path))

    @output.setter
    def output(self, value: str):
        """Get or set the output file path."""
        self._output = value


    # ---------- IP generation ----------

    def _rand_private_ip(self) -> str:
        base = random.choice(self.PRIVATE_IP_RANGES)
        return f"{base[0]}.{base[1]}.{random.randint(0, 255)}.{random.randint(1, 254)}"

    def _rand_public_ip(self) -> str:
        # Very simple: generate IP and avoid typical private/reserved ranges
        while True:
            o1 = random.randint(1, 254)
            o2 = random.randint(0, 255)
            o3 = random.randint(0, 255)
            o4 = random.randint(1, 254)

            # exclude private/common ranges
            if o1 == 10:
                continue
            if o1 == 127:
                continue
            if o1 == 192 and o2 == 168:
                continue
            if o1 == 172 and 16 <= o2 <= 31:
                continue
            if o1 == 169 and o2 == 254:
                continue
            if 224 <= o1 <= 239:  # multicast
                continue

            return f"{o1}.{o2}.{o3}.{o4}"

    def _get_client_ip(self) -> str:
        # 70% already seen IP ("loyal" client), 30% new
        if self._client_ips and random.random() < 0.7:
            return random.choice(self._client_ips)

        # new IP
        if random.random() < 0.5:
            ip = self._rand_private_ip()
        else:
            ip = self._rand_public_ip()

        if len(self._client_ips) < self.max_clients:
            self._client_ips.append(ip)
        else:
            # replace some random one
            idx = random.randrange(len(self._client_ips))
            self._client_ips[idx] = ip

        return ip

    # ---------- URL / host generation ----------

    def _choose_host(self) -> str:
        # more weight to www / shop
        return random.choice(self.HOSTS)

    def _choose_path_for_host(self, host: str) -> str:
        common = [
            "/",
            "/index.html",
            "/favicon.ico",
            "/robots.txt",
            "/sitemap.xml",
            "/login",
            "/logout",
            "/signup",
            "/buscar",
        ]

        tienda = [
            "/productos",
            "/productos/1234",
            "/productos/5678",
            "/carrito",
            "/checkout",
        ]

        api = [
            "/api/v1/users",
            "/api/v1/users/123",
            "/api/v1/items",
            "/api/v1/items/42",
            "/api/v2/orders",
        ]

        static = [
            "/static/css/style.css",
            "/static/js/app.js",
            "/static/img/logo.png",
            "/static/img/banner.jpg",
        ]

        attackish = [
            "/wp-login.php",
            "/xmlrpc.php",
            "/phpmyadmin/",
            "/.env",
            "/.git/config",
        ]

        pool: List[str] = common.copy()

        if host.startswith("tienda."):
            pool += tienda * 3
        if host.startswith("api."):
            pool += api * 4
        if host.startswith("static."):
            pool += static * 4

        # from time to time, scans/probes
        if random.random() < 0.1:
            pool += attackish

        return random.choice(pool)

    # ---------- otras piezas ----------

    def _choose_method(self) -> str:
        methods = list(self.METHODS.keys())
        weights = list(self.METHODS.values())

        # if only one method, return it directly (testing convenience)
        if len(methods) == 1:
            return methods[0]

        return random.choices(methods, weights=weights, k=1)[0]

    def _choose_status(self) -> int:
        codes = list(self.STATUS_DISTRIBUTION.keys())
        weights = [self.STATUS_DISTRIBUTION[c]["weight"] for c in codes]
        code = random.choices(codes, weights=weights, k=1)[0]
        cfg = self.STATUS_DISTRIBUTION[code]
        return code, cfg

    def _choose_referrer(self, host: str) -> str:
        # mostly no referrer, sometimes search engines, sometimes own site
        r = random.random()
        if r < 0.6:
            return "-"
        if r < 0.8:
            return random.choice(self.REFERRERS)
        # internal traffic
        return f"https://{host}/"

    def _estimate_size(self, path: str, status: int) -> int:
        if status >= 400:
            return random.randint(200, 2000)
        if path.endswith((".css", ".js")):
            return random.randint(5_000, 100_000)
        if path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return random.randint(20_000, 500_000)
        if path in ("/", "/index.html"):
            return random.randint(2_000, 20_000)
        return random.randint(500, 15_000)

    def _gen_line(self) -> str:
        """ Generate a single log line. """
        ts = time.strftime('[%d/%b/%Y:%H:%M:%S %z]')

        status, status_cfg = self._choose_status()
        method = self._choose_method()
        scheme = random.choice(["http", "https"])
        host = self._choose_host()
        path = self._choose_path_for_host(host)
        client_ip = self._get_client_ip()

        # size by config (e.g. 499 -> 0)
        if status_cfg.get("length_zero", False):
            size = 0
        else:
            size = self._estimate_size(path, status)

        gzip_flag = "-"

        if host.startswith("www."):
            upstream_host = host.replace("www.", "srv.", 1)
        else:
            upstream_host = f"{host}.srv"

        ua = random.choice(self.USER_AGENTS)
        ref = self._choose_referrer(host)

        # header according to "header_mode"
        header_mode = status_cfg.get("header_mode", "normal")

        if header_mode == "499":
            # [time] - - 499 -
            f1, f2, f3, f4 = "-", "-", "499", "-"
        else:
            # [time] - 200 200 -
            f1, f2, f3, f4 = "-", str(status), str(status), "-"

        line = (
            f'{ts} {f1} {f2} {f3} {f4} '
            f'{method} {scheme} {host} "{path}" '
            f'[Client {client_ip}] [Length {size}] [Gzip {gzip_flag}] '
            f'[Sent-to {upstream_host}] "{ua}" "{ref}"\n'
        )

        return line

    # ---------- writing loop ----------

    def _run(self):
        while self._running:
            batch_size = random.randint(self.min_batch, self.max_batch)

            for _ in range(batch_size):
                line = self._gen_line()
                self._write_line(line)

                # small pauses within the burst
                if random.random() < 0.2:
                    time.sleep(random.uniform(0.01, 0.05))

            # average interval with jitter
            sleep_time = random.uniform(
                self.base_interval * 0.5,
                self.base_interval * 1.5,
            )
            time.sleep(sleep_time)


    def _write_line(self, line: str):
        if self.output == "":
            print("[FakeLogGen] Output file not set.", flush=True)
            return

        if self.debug:
            print(f"[FakeLogGen] {line.strip()}", flush=True)

        with open(self.output, "a", encoding="utf-8") as f:
            f.write(line)

    # ---------- control ----------

    def start(self):
        """Start generating logs in a background thread."""
        if self._running:
            return

        if not self.output:
            print("[FakeLogGen] Output file not set. Cannot start.", flush=True)
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            daemon=True
        )

        self._thread.start()

        if self.debug:
            print("[FakeLogGen] Starting log generation...", flush=True)


    def stop(self):
        """Stop generating logs."""
        self._running = False
        if self._thread:
            self._thread.join()
            self._thread = None

        if self.debug:
            print("[FakeLogGen] Stopping log generation...", flush=True)

if __name__ == "__main__":
    # quick example
    # gen = NginxLogGenerator(
    #     output="access_simulado.log",
    #     base_interval=0.5,   # media aprox entre bursts
    #     min_batch=1,
    #     max_batch=8,
    # )
    # gen.start()
    # try:
    #     print("Generando logs... Ctrl+C para parar")
    #     while True:
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     print("\nParando...")
    #     gen.stop()
    pass
