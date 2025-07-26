// Initialize Leaflet map
const map = L.map('map').setView([17.3850, 78.4867], 13); // Default: Hyderabad
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19
}).addTo(map);

// Custom icons
const userIcon = L.divIcon({
    className: 'user-icon',
    html: '<div style="background-color: blue; width: 12px; height: 12px; border-radius: 50%; border: 2px solid white;"></div>',
    iconSize: [12, 12]
});

const restaurantIcon = L.divIcon({
    className: 'restaurant-icon',
    html: '<div style="background-color: red; width: 12px; height: 12px; border-radius: 50%; border: 2px solid white;"></div>',
    iconSize: [12, 12]
});

// Variables
let userMarker = null;
let restaurantMarkers = [];
const GEOAPIFY_API_KEY = 'YOUR_GEOAPIFY_API_KEY'; // Replace with your key from https://myprojects.geoapify.com

// Haversine distance calculation
function getDistance(lat1, lon1, lat2, lon2) {
    const R = 6371; // Earth's radius in km
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c; // Distance in km
}

// Fetch nearby restaurants
async function fetchRestaurants(lat, lon, cuisine = '') {
    const url = `https://api.geoapify.com/v2/places?categories=catering.restaurant&filter=circle:${lon},${lat},5000&limit=20&apiKey=${GEOAPIFY_API_KEY}${cuisine ? `&conditions=${cuisine}` : ''}`;
    try {
        const response = await fetch(url);
        const data = await response.json();
        return data.features.map(feature => ({
            name: feature.properties.name || 'Unknown Restaurant',
            lat: feature.geometry.coordinates[1],
            lon: feature.geometry.coordinates[0],
            address: feature.properties.address_line2 || 'No address',
            cuisine: feature.properties.datasource?.raw?.cuisine || 'N/A',
            distance: getDistance(lat, lon, feature.geometry.coordinates[1], feature.geometry.coordinates[0])
        }));
    } catch (error) {
        console.error('Error fetching restaurants:', error);
        return [];
    }
}

// Update restaurant markers
function updateRestaurants(restaurants) {
    restaurantMarkers.forEach(marker => map.removeLayer(marker));
    restaurantMarkers = [];
    restaurants.forEach(restaurant => {
        const marker = L.marker([restaurant.lat, restaurant.lon], { icon: restaurantIcon })
            .addTo(map)
            .bindPopup(`
                <b>${restaurant.name}</b><br>
                Cuisine: ${restaurant.cuisine}<br>
                Address: ${restaurant.address}<br>
                Distance: ${restaurant.distance.toFixed(2)} km
            `);
        restaurantMarkers.push(marker);
    });
}

// Update user position
function updateUserPosition(position) {
    const { latitude, longitude } = position.coords;
    document.getElementById('status').textContent = `Location: ${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;

    if (userMarker) {
        userMarker.setLatLng([latitude, longitude]);
    } else {
        userMarker = L.marker([latitude, longitude], { icon: userIcon }).addTo(map);
        map.setView([latitude, longitude], 15);
    }

    fetchRestaurants(latitude, longitude).then(updateRestaurants);
}

// Handle geolocation errors
function handleError(error) {
    document.getElementById('status').textContent = `Error: ${error.message}`;
}

// Start real-time tracking
if (navigator.geolocation) {
    navigator.geolocation.watchPosition(updateUserPosition, handleError, {
        enableHighAccuracy: true,
        timeout: 5000,
        maximumAge: 0
    });
} else {
    document.getElementById('status').textContent = 'Geolocation not supported!';
}

// Filter by cuisine
document.getElementById('filterBtn').addEventListener('click', () => {
    if (userMarker) {
        const cuisine = document.getElementById('cuisineFilter').value.trim();
        const lat = userMarker.getLatLng().lat;
        const lon = userMarker.getLatLng().lng;
        fetchRestaurants(lat, lon, cuisine).then(updateRestaurants);
    } else {
        alert('Please wait for your location to load!');
    }
});