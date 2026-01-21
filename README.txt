# Bite Me Buddy - Admin Orders Management

A comprehensive admin dashboard for managing orders, customers, payments, and analytics for the Bite Me Buddy service.

## Key Changes from Previous Version

### Removed Google Maps API Dependency
- **Removed**: Google Maps API key requirement
- **Added**: OpenStreetMap integration using Leaflet.js
- **Benefits**: No API key needed, free to use, privacy-friendly
- **Features**: 
  - Interactive maps in customer details
  - Clickable OpenStreetMap links
  - Static map previews
  - No usage limits or billing

### Enhanced Features
1. **JavaScript-based Maps**: Using Leaflet.js with OpenStreetMap tiles
2. **Interactive Maps**: Zoomable, draggable maps in modals
3. **No API Keys**: Completely free and open-source mapping
4. **Better Privacy**: Customer location data stays private
5. **Offline Capable**: Maps can work with local tile servers if needed

## Installation & Setup

1. **Clone and install dependencies**:
```bash
git clone <repository-url>
cd bite-me-buddy-admin
pip install -r requirements.txt