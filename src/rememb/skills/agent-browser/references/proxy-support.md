# Proxy Support

Proxy configuration for geo-testing, rate limiting avoidance, and corporate environments.

**Related**: [commands.md](commands.md) for global options, [SKILL.md](../SKILL.md) for quick start.

## Contents

- [Basic Proxy Configuration](#basic-proxy-configuration)
- [Authenticated Proxy](#authenticated-proxy)
- [SOCKS Proxy](#socks-proxy)
- [Proxy Bypass](#proxy-bypass)
- [Common Use Cases](#common-use-cases)
- [Verifying Proxy Connection](#verifying-proxy-connection)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

## Basic Proxy Configuration

Use the `--proxy` flag or set proxy via environment variable:

```bash
# Via CLI flag
agent-browser --proxy "<proxy-url>" open <page-url>

# Via environment variable
export HTTP_PROXY="<proxy-url>"
agent-browser open <page-url>

# HTTPS proxy
export HTTPS_PROXY="<secure-proxy-url>"
agent-browser open <page-url>

# Both
export HTTP_PROXY="<proxy-url>"
export HTTPS_PROXY="<proxy-url>"
agent-browser open <page-url>
```

## Authenticated Proxy

For proxies requiring authentication:

```bash
# Include credentials in URL
export HTTP_PROXY="http://<proxy-user>:<proxy-password>@<proxy-host>:<proxy-port>"
agent-browser open <page-url>
```

## SOCKS Proxy

```bash
# SOCKS5 proxy
export ALL_PROXY="socks5://<proxy-host>:<proxy-port>"
agent-browser open <page-url>

# SOCKS5 with auth
export ALL_PROXY="socks5://<proxy-user>:<proxy-password>@<proxy-host>:<proxy-port>"
agent-browser open <page-url>
```

## Proxy Bypass

Skip proxy for specific domains using `--proxy-bypass` or `NO_PROXY`:

```bash
# Via CLI flag
agent-browser --proxy "<proxy-url>" --proxy-bypass "localhost,*.internal.test" open <page-url>

# Via environment variable
export NO_PROXY="localhost,127.0.0.1,.internal.test"
agent-browser open https://intranet.internal.test  # Direct connection
agent-browser open <external-url>                  # Via proxy
```

## Common Use Cases

### Geo-Location Testing

```bash
#!/bin/bash
# Test site from different regions using geo-located proxies

PROXIES=(
    "http://us-proxy.internal.test:8080"
    "http://eu-proxy.internal.test:8080"
    "http://asia-proxy.internal.test:8080"
)

for proxy in "${PROXIES[@]}"; do
    export HTTP_PROXY="$proxy"
    export HTTPS_PROXY="$proxy"

    region=$(echo "$proxy" | grep -oP '^\w+-\w+')
    echo "Testing from: $region"

    agent-browser --session "$region" open <page-url>
    agent-browser --session "$region" screenshot "./screenshots/$region.png"
    agent-browser --session "$region" close
done
```

### Rotating Proxies for Scraping

```bash
#!/bin/bash
# Rotate through proxy list to avoid rate limiting

PROXY_LIST=(
    "http://proxy1.internal.test:8080"
    "http://proxy2.internal.test:8080"
    "http://proxy3.internal.test:8080"
)

URLS=(
    "https://site.com/page1"
    "https://site.com/page2"
    "https://site.com/page3"
)

for i in "${!URLS[@]}"; do
    proxy_index=$((i % ${#PROXY_LIST[@]}))
    export HTTP_PROXY="${PROXY_LIST[$proxy_index]}"
    export HTTPS_PROXY="${PROXY_LIST[$proxy_index]}"

    agent-browser open "${URLS[$i]}"
    agent-browser get text body > "output-$i.txt"
    agent-browser close

    sleep 1  # Polite delay
done
```

### Corporate Network Access

```bash
#!/bin/bash
# Access internal sites via corporate proxy

export HTTP_PROXY="http://corpproxy.internal.test:8080"
export HTTPS_PROXY="http://corpproxy.internal.test:8080"
export NO_PROXY="localhost,127.0.0.1,.internal.test"

# External sites go through proxy
agent-browser open <external-url>

# Internal sites bypass proxy
agent-browser open https://intranet.internal.test
```

## Verifying Proxy Connection

```bash
# Check your apparent IP
agent-browser open https://httpbin.org/ip
agent-browser get text body
# Should show proxy's IP, not your real IP
```

## Troubleshooting

### Proxy Connection Failed

```bash
# Test proxy connectivity first
curl -x <proxy-url> https://httpbin.org/ip

# Check if proxy requires auth
export HTTP_PROXY="http://<proxy-user>:<proxy-password>@<proxy-host>:<proxy-port>"
```

### SSL/TLS Errors Through Proxy

Some proxies perform SSL inspection. If you encounter certificate errors:

```bash
# For testing only - not recommended for production
agent-browser open <page-url> --ignore-https-errors
```

### Slow Performance

```bash
# Use proxy only when necessary
export NO_PROXY="*.cdn.com,*.static.com"  # Direct CDN access
```

## Best Practices

1. **Use environment variables** - Don't hardcode proxy credentials
2. **Set NO_PROXY appropriately** - Avoid routing local traffic through proxy
3. **Test proxy before automation** - Verify connectivity with simple requests
4. **Handle proxy failures gracefully** - Implement retry logic for unstable proxies
5. **Rotate proxies for large scraping jobs** - Distribute load and avoid bans
