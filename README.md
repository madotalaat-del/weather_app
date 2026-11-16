# Skyline Weather

A small Flask app that looks up a city and displays its current weather using Open-Meteo. No API key is required.

Weather lookups are cached in memory for 10 minutes. The home route is limited to 30 requests per minute and 120 per hour per client address. These defaults suit local use; multi-worker deployments should configure shared cache and rate-limit storage (for example Redis).

## Run locally

From this directory, install the dependencies and start the server:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>, search for a city, or select **Use My Location** and allow the browser's location prompt. The app needs an internet connection to contact Open-Meteo. The browser location feature is available on localhost or another secure origin (HTTPS).

The results include current conditions and a five-day daily forecast. Background colors and weather icons adapt to the reported conditions.

## Run tests

From the `weather_app` directory:

```powershell
python -m unittest discover -s tests -v
```

## Run in Docker

```powershell
docker build -t skyline-weather .
docker run --rm -p 5000:5000 skyline-weather
```

The container runs the app with Waitress, a production WSGI server.

## Deploy on Render

The included `render.yaml` configures a Docker-based web service. Make this directory the root of a repository, push it to a Git provider, then create a Render Blueprint from that repository. Render will build the Docker image and use its assigned `PORT`.

The default cache and rate-limit stores are in-memory and work for a single instance. For multiple instances, configure a shared Redis service with `CACHE_TYPE=RedisCache`, `CACHE_REDIS_URL`, and `RATELIMIT_STORAGE_URI`.
