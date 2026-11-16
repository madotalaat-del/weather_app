const locationButton = document.querySelector("#use-location");
const locationStatus = document.querySelector("#location-status");

if (locationButton && locationStatus) {
  locationButton.addEventListener("click", () => {
    if (!navigator.geolocation) {
      locationStatus.textContent = "Your browser does not support location services.";
      return;
    }

    locationButton.disabled = true;
    locationStatus.textContent = "Getting your location...";
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        locationStatus.textContent = "Loading your local forecast...";
        try {
          const response = await fetch("/", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({
              latitude: String(coords.latitude),
              longitude: String(coords.longitude),
            }),
          });
          const html = await response.text();
          const nextDocument = new DOMParser().parseFromString(html, "text/html");
          const nextResult = nextDocument.querySelector("#weather-result");
          const currentResult = document.querySelector("#weather-result");
          if (!nextResult || !currentResult) {
            throw new Error("Weather data could not be displayed. Please try again.");
          }

          currentResult.replaceWith(document.importNode(nextResult, true));
          document.body.className = nextDocument.body.className;
          const serverError = document.querySelector("#weather-result [role='alert']");
          locationStatus.textContent = serverError
            ? serverError.textContent
            : "Showing weather for your location.";
          if (!response.ok && !serverError) {
            throw new Error("Weather data could not be loaded. Please try again.");
          }
        } catch (error) {
          locationStatus.textContent = error.message;
        } finally {
          locationButton.disabled = false;
        }
      },
      (error) => {
        const messages = {
          1: "Location permission was denied. Allow access in your browser settings or search for a city.",
          2: "Your location is unavailable right now. Please try again or search for a city.",
          3: "Location lookup timed out. Please try again.",
        };
        locationStatus.textContent = messages[error.code]
          || "Could not get your location. Please try again.";
        locationButton.disabled = false;
      },
      { enableHighAccuracy: false, maximumAge: 300000, timeout: 15000 },
    );
  });
}
