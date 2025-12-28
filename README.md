<div style="text-align:center;">
  <img src="https://img.shields.io/github/v/tag/vsc55/npmGrafStats" alt="GitHub tag">
  <img src="https://img.shields.io/github/last-commit/vsc55/npmGrafStats/python" alt="Last Commit (python branch)">
  <img src="https://img.shields.io/github/actions/workflow/status/vsc55/npmGrafStats/docker-test.yml?tags=test" alt="Workflow Status">
  <img src="https://img.shields.io/github/languages/code-size/vsc55/npmGrafStats" alt="Code Size in Bytes">
  <img src="https://img.shields.io/github/languages/count/vsc55/npmGrafStats" alt="Languages">
  <img src="https://img.shields.io/github/languages/top/vsc55/npmGrafStats" alt="Top Language">
  <a href="https://hub.docker.com/r/vsc55/npmgraf">
    <img src="https://img.shields.io/docker/pulls/vsc55/npmgraf" alt="Docker Pulls">
  </a>
  <a href="https://hub.docker.com/r/vsc55/npmgraf">
    <img src="https://img.shields.io/docker/image-size/vsc55/npmgraf/test" alt="Docker Image Size (test)">
  </a>
  <img src="https://img.shields.io/maintenance/yes/2025" alt="Maintenance">
  <a href="https://github.com/vsc55/npmGrafStats/blob/python/LICENSE">
    <img src="https://img.shields.io/github/license/vsc55/npmGrafStats" alt="License">
  </a>
  <a href="https://github.com/vsc55/npmGrafStats/stargazers">
    <img src="https://img.shields.io/github/stars/vsc55/npmGrafStats?style=social" alt="GitHub Stars">
  </a>
</div>

# npmGrafStats (Python)

This project analyzes the logs of **Nginx Proxy Manager** and exports them to **InfluxDB** to be used in a **Grafana dashboard**.

This repository is a **fork of [smilebasti/npmGrafStats](https://github.com/smilebasti/npmGrafStats/tree/main)** and has been:

- **completely rewritten from scratch in Python**
- refactored to use a **multi-threaded** architecture

The goal is to keep the original behaviour (parsing NPM logs and feeding InfluxDB/Grafana) while simplifying the runtime and improving performance.

---

## What it does

`npmGrafStats` processes **Reverse Proxy** and/or **Redirection** logs from Nginx Proxy Manager.  
It can also **exclude specific IPs** (for example external monitoring services) from being written to InfluxDB.

The exported data can be visualized in Grafana dashboards, similar to the original project.

---

## Features

This Python rewrite includes all key features from the original project, plus several performance and reliability improvements:

### Core Features

- 📈 **Real-time statistics** exported to InfluxDB for use in Grafana
- 🧩 **Support for Nginx Proxy Manager**
- 🌐 **GeoIP integration** using `GeoLite2-City.mmdb` and `GeoLite2-ASN.mmdb`
- 📍 **AbuseIPDB** check ip in AbuseIPDBN and implement cache.
- ⚙️ **Configurable log sources** for multiple proxy hosts or redirect logs
- 🚫 **Exclude unwanted IPs** (e.g. uptime checks, monitoring services)
- 🕓 **Accurate measurement timestamps** for each parsed request
- 🧠 **Tagging and aggregation** for Grafana dashboards (source IP, target IP, domain, location, etc...).
  - 🔔 **New!** Status Code, Uri, Method (GET, POST, etc...), Scheme, User Agent.

### Enhancements in the Python version

- 🧵 **Multi-threaded log parsing** and InfluxDB writes for better performance
- 🐍 **Pure Python code** using only code python
- ⚡ **Optimized I/O** for handling large or continuous log files
- 🔒 **Simpler configuration and deployment** via Docker and environment variables
- 🧰 **Cross-platform** (Linux, macOS, Windows, ARM/AMD64 compatible)
- 💾 **Lightweight footprint** — minimal CPU and memory usage
- 🔁 **Continuous monitoring mode** for real-time ingestion of new log entries

---

## Data extracted from the logs

Each log entry produces a structured record containing:

- **Source IP**
- **Target IP/FQDN** (internal NPM mapping)
- **Domain name**
- **Timestamp**
- **AbuseIPDB**
- **StatusCode**
- **Method**
- **Scheme**
- **User Agent**
- **Length**
- **Uri**
- **GeoIP data** (from `GeoLite2-City.mmdb` if enabled):
  - Country
  - Coordinates
  - City
- **GeoIP data** (from `GeoLite2-ASN.mmdb` if enabled):
  - Organizatio

> Note: GeoIP requires a valid `GeoLite2-City.mmdb` and `GeoLite2-ASN.mmdb` files and configured paths.

---

## Installation (Docker)

### Requirements

- **Docker** and (optionally) **Docker Compose**
- Access to Nginx Proxy Manager log files
- **InfluxDB** instance
- (Optional) **Grafana** for visualization

### Quick Start

```bash
docker run -d \
  --name npmgrafstats \
  -v /path/to/npm/logs:/logs:ro \
  -v /path/to/GeoLite2-City.mmdb:/geoip/GeoLite2-City.mmdb:ro \
  -v /path/to/GeoLite2-ASN.mmdb:/geoip/GeoLite2-ASN.mmdb:ro \
  -e INFLUX_URL=http://influxdb:8086 \
  -e INFLUX_ORG=your-org \
  -e INFLUX_BUCKET=npm \
  -e INFLUX_TOKEN=your-token \
  -e GEO_CITY_DB_PATH=/geoip/GeoLite2-City.mmdb \
  -e GEO_ASN_DB_PATH=/geoip/GeoLite2-ASN.mmdb \
  --restart unless-stopped \
  vsc55/npmgraf:test
```

### Docker Compose Example

```yaml
services:
  npmgrafstats:
    image: vsc55/npmgraf:test
    container_name: npmgrafstats
    restart: unless-stopped
    volumes:
      - /path/to/npm/logs:/logs:ro
      - /path/to/GeoLite2-City.mmdb:/geoip/GeoLite2-City.mmdb:ro
    environment:
      INFLUX_URL: http://influxdb:8086
      INFLUX_ORG: your-org
      INFLUX_BUCKET: npm
      INFLUX_TOKEN: your-token

      GEO_CITY_DB_PATH: /geoip/GeoLite2-City.mmdb
```

After starting, the container will continuously read NPM logs, process them in parallel, and export the data to your InfluxDB instance.

---

## Configuration

All configuration is done through environment variables:

| Variable | Description |
| ----------- | -------------- |
| `INFLUX_URL` | URL of your InfluxDB instance |
| `INFLUX_ORG` | Organization name (InfluxDB v2) (default `npmgrafstats`) |
| `INFLUX_BUCKET` | Target bucket/database (default `npmgrafstats`) |
| `INFLUX_TOKEN` | InfluxDB API token |
| `INFLUX_RETRY_CONNECT` | (default `10`) |
| `INFLUX_RETRY_DELAY` | (default `5`) |
| `ABUSEIP_KEY` | API key for AbuseIPDB (if used) |
| `ABUSEIP_CACHE_EXPIRE` | Expiration time in minutes for AbuseIPDB cache (default: `2880`) |
| `ABUSEIP_CACHE_FILE` | Path to AbuseIPDB cache file (default: `/data/abuseipdb_cache.json`) |
| `GEO_ASN_DB_PATH` | Path to `GeoLite2-ASN.mmdb` (default `/geolite/GeoLite2-ASN.mmdb`) |
| `GEO_CITY_DB_PATH` | Path to `GeoLite2-City.mmdb` (default `/geolite/GeoLite2-City.mmdb`) |
| `MONITORING_FILE_PATH` | File Monotoring IP's, (default `/data/monitoringips.txt`) |
| `NPM_LOGS_PATH` | Path to Nginx Proxy Manager logs (default `/logs`) |
| `PROXY_LOGS` | Enable proxy logs (default `true`) |
| `REDIRECT_LOGS` | Enable redirection logs (default `true`) |
| `MONITORING_LOGS` | Enable monitoring logs (default `false`) |
| `PUBLIC_LOGS` | Enable public logs (default `true`) |
| `INTERNAL_LOGS` | Enable internal logs (default `false`) |
| `LOG_LEVEL` | Global log level (default `INFO`) |
| `LOG_CONSOLE_LEVEL` | Console log level (default `INFO`) |
| `LOG_FILE_LEVEL` | File log level (default `DEBUG`) |
| `LOG_FILE` | Path to log file (default: None) |

**Note:** The supported log levels are `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

---

## InfluxDB & Grafana

The exported data structure is designed to remain compatible with the original npmGrafStats dashboards:

- Measurement name: `npm_requests`,
- Tags: `Ip`, `Target`, `Domain`, `Statuscode`, `Method`, `Scheme`, `Agent`, `Key`, `City`, `State`, `Name`, `Latitude`, `Longitude`, `Asn`, `Abuse_Confidence_Score`, `Abuse_Total_Reports`
- Fields: `ip`, `target`, `domain`, `statuscode`, `method`, `scheme`, `agent`, `uri`, `length`, `metric`, `key`, `city`, `state`, `name`,  `latitude`, `longitude`,  `asn`, `abuse_confidence_score`, `abuse_total_reports`

> ---
> ⚠️ **Important notice**
>
> With the migration to the new system, changes have been made to the structure of **tags** and **fields** in InfluxDB.
>
> These changes are **not 100% compatible with previous versions**, therefore:
>
> - Existing queries may stop working or return different results.  
> - Dashboards and scripts may require updates.  
> - Integrations depending on the previous schema may be affected.
>
> It is strongly recommended to **review and validate queries, dashboards, and data pipelines** before assuming full backward compatibility.
>
> ---

Example Grafana view after a few hours of data collection:

![npmGrafStats Dashboard](https://user-images.githubusercontent.com/60941345/203383131-50b7197e-2e58-4bb1-a7e6-d92e15d3430a.png)

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=vsc55/npmGrafStats&type=Date)](https://star-history.com/#vsc55/npmGrafStats&Date)

---

## Source

- Original repository: [smilebasti/npmGrafStats](https://github.com/smilebasti/npmGrafStats)  

This Python rewrite is an independent implementation maintained separately.
