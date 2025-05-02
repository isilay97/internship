import csv
import requests
import json
import time
import argparse
import os
import re
import math
import sys
import concurrent.futures
import logging
from datetime import datetime
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"business_finder_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# here is the main abstract class that we will use to create the other classes
# the main purpose of this class is to define the methods that will be used in the other classes
class BusinessDataAPI(ABC):
    """Base abstract class for business data APIs"""

    @abstractmethod
    def search_businesses(self,
                          location: str,
                          category: str,
                          radius_km: int,
                          min_rating: float) -> List[Dict[Any, Any]]:
        """
        Search for businesses based on criteria

        Args:
            location: City or country to search in
            category: Type of business (Hotel, Restaurant, Bar, etc.)
            radius_km: Search radius in kilometers
            min_rating: Minimum Google rating

        Returns:
            List of business data dictionaries
        """
        pass

    @abstractmethod
    def get_api_name(self) -> str:
        """Returns the name of the API source"""
        pass

    def extract_email_from_website(self, website_url: str) -> Optional[str]:
        """
        Attempt to extract email from website content

        Args:
            website_url: URL of the business website

        Returns:
            Email address if found, None otherwise
        """
        if not website_url:
            return None

        try:
            response = requests.get(website_url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            if response.status_code == 200:
                # Simple regex for email extraction
                email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                emails = re.findall(email_pattern, response.text)

                if emails:
                    # Filter out common false positives
                    valid_emails = [
                        email for email in emails
                        if not any(exclude in email.lower() for exclude in
                                   ['example.com', 'yourdomain', 'domain.com', 'email.com'])
                    ]

                    if valid_emails:
                        return valid_emails[0]

            # Try contact page if available
            if '/contact' not in website_url.lower():
                contact_url = website_url.rstrip('/') + '/contact'
                contact_response = requests.get(contact_url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                })

                if contact_response.status_code == 200:
                    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                    emails = re.findall(email_pattern, contact_response.text)

                    if emails:
                        valid_emails = [
                            email for email in emails
                            if not any(exclude in email.lower() for exclude in
                                       ['example.com', 'yourdomain', 'domain.com', 'email.com'])
                        ]

                        if valid_emails:
                            return valid_emails[0]

        except Exception as e:
            logger.debug(f"Error extracting email from {website_url}: {e}")

        return None


class GooglePlacesAPI(BusinessDataAPI):
    """Google Places API implementation"""

    def __init__(self, api_key: str):
        """
        Initialize with Google API key

        Args:
            api_key: Google Places API key
        """
        self.api_key = api_key
        self.base_url = "https://maps.googleapis.com/maps/api/place"
        self.request_count = 0
        self.last_request_time = 0

    # in here we are defining the get_api_name method that will return the name of the api
    # koofti pool mikhad!!!
    def get_api_name(self) -> str:
        return "Google Places API"

    def _handle_rate_limit(self):
        """Manage request rate to avoid hitting API limits"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        # Google Places API has a limit of 50 requests per second
        # Adding a safety margin, we'll limit to 10 requests per second
        if time_since_last_request < 0.1 and self.request_count > 0:
            time.sleep(0.1 - time_since_last_request)

        self.request_count += 1
        self.last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[Any, Any]:
        """
        Make a request to the Google Places API

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            JSON response as dictionary
        """
        self._handle_rate_limit()

        params['key'] = self.api_key
        url = f"{self.base_url}/{endpoint}/json"

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making request to Google Places API: {e}")
            return {"status": "ERROR", "error_message": str(e)}

    def _get_place_details(self, place_id: str) -> Dict[Any, Any]:
        """
        Get detailed information about a place

        Args:
            place_id: Google Place ID

        Returns:
            Place details as dictionary
        """
        params = {
            'place_id': place_id,
            'fields': 'name,formatted_address,formatted_phone_number,website,rating,user_ratings_total,geometry,address_components'
        }

        return self._make_request('details', params)

    def search_businesses(self,
                          location: str,
                          category: str,
                          radius_km: int,
                          min_rating: float) -> List[Dict[Any, Any]]:
        """
        Search for businesses based on criteria

        Args:
            location: City or country to search in
            category: Type of business (Hotel, Restaurant, Bar, etc.)
            radius_km: Search radius in kilometers
            min_rating: Minimum Google rating

        Returns:
            List of business data dictionaries
        """
        # Convert km to meters for Google API
        radius_meters = radius_km * 1000

        # Map category to appropriate Google Places type
        category_map = {
            'hotel': 'lodging',
            'restaurant': 'restaurant',
            'bar': 'bar',
            'cafe': 'cafe',
            'bakery': 'bakery',
            'nightclub': 'night_club'
        }
        # in this section we are mapping the category to the google places category
        # for example if the user wants to search for hotels we will map it to lodging
        # because lodging is the category that google places uses for hotels
        google_type = category_map.get(category.lower(), category.lower())

        # First, perform geocoding to get coordinates for the location
        geocode_params = {
            'address': location
        }

        geocode_result = self._make_request('geocode', geocode_params)

        if geocode_result.get('status') != 'OK':
            logger.error(
                f"Geocoding failed for location '{location}': {geocode_result.get('error_message', 'Unknown error')}")
            return []

        location_coords = geocode_result['results'][0]['geometry']['location']

        # Now search for places
        search_params = {
            'location': f"{location_coords['lat']},{location_coords['lng']}",
            'radius': radius_meters,
            'type': google_type
        }

        search_result = self._make_request('nearbysearch', search_params)
        # if the search result status is not ok then we will log an error message
        # and return an empty list
        if search_result.get('status') != 'OK':
            logger.error(f"Places search failed: {search_result.get('error_message', 'Unknown error')}")
            return []

        # Process results and get details for each place
        businesses = []

        for place in search_result.get('results', []):
            # Skip places with too low rating
            if 'rating' in place and place['rating'] < min_rating:
                continue

            # Get detailed information
            details_result = self._get_place_details(place['place_id'])

            if details_result.get('status') != 'OK':
                logger.warning(
                    f"Failed to get details for place {place['name']}: {details_result.get('error_message', 'Unknown error')}")
                continue

            place_details = details_result['result']

            # Extract address components
            address_components = place_details.get('address_components', [])
            city = ''
            country = ''

            for component in address_components:
                if 'locality' in component['types']:
                    city = component['long_name']
                elif 'country' in component['types']:
                    country = component['long_name']

            # Construct business data
            business_data = {
                'Business Name': place_details.get('name', ''),
                'Category': category.capitalize(),
                'Address': place_details.get('formatted_address', ''),
                'City': city,
                'Country': country,
                'Phone Number': place_details.get('formatted_phone_number', ''),
                'Email': '',  # Will try to extract from website
                'Website': place_details.get('website', ''),
                'Google Rating': place_details.get('rating', ''),
                'Number of Reviews': place_details.get('user_ratings_total', ''),
                'Latitude': place_details.get('geometry', {}).get('location', {}).get('lat', ''),
                'Longitude': place_details.get('geometry', {}).get('location', {}).get('lng', ''),
                'API Source': self.get_api_name()
            }

            # Try to extract email from website if available
            if business_data['Website']:
                email = self.extract_email_from_website(business_data['Website'])
                if email:
                    business_data['Email'] = email

            businesses.append(business_data)

            # Check if we have pagination with a next_page_token
            if 'next_page_token' in search_result:
                # Need to wait a bit before using the next_page_token
                time.sleep(2)

                next_params = {
                    'pagetoken': search_result['next_page_token']
                }

                next_result = self._make_request('nearbysearch', next_params)

                if next_result.get('status') == 'OK':
                    search_result = next_result
                else:
                    break

        return businesses


# the openstreetmap api is a free alternative to the google places api

class OpenStreetMapAPI(BusinessDataAPI):
    """OpenStreetMap API implementation (free alternative)"""

    def __init__(self):
        """Initialize the OpenStreetMap API client"""
        self.base_url = "https://nominatim.openstreetmap.org"
        self.request_count = 0
        self.last_request_time = 0

    def get_api_name(self) -> str:
        return "OpenStreetMap API"

    def _handle_rate_limit(self):
        """
        Manage request rate to avoid hitting API limits
        OpenStreetMap has a limit of 1 request per second
        """
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < 1.0 and self.request_count > 0:
            time.sleep(1.0 - time_since_last_request)

        self.request_count += 1
        self.last_request_time = time.time()

    # here we are going to make a request to the openstreetmap api
    # we will pass the endpoint and the parameters to the request
    # and then we will get the response as a json object
    # if there is an error we will log the error and return an empty dictionary
    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[Any, Any]:
        """
        Make a request to the OpenStreetMap API

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            JSON response as dictionary
        """
        self._handle_rate_limit()

        # Add required headers for OSM API
        headers = {
            'User-Agent': 'HospitalityBusinessFinder/1.0',
            'Accept': 'application/json'
        }

        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making request to OpenStreetMap API: {e}")
            return {"error": str(e)}

    # here we are going to search for businesses based on the these criterria
    def search_businesses(self,
                          location: str,
                          category: str,
                          radius_km: int,
                          min_rating: float) -> List[Dict[Any, Any]]:
        """
        Search for businesses based on criteria

        Args:
            location: City or country to search in
            category: Type of business (Hotel, Restaurant, Bar, etc.)
            radius_km: Search radius in kilometers
            min_rating: Minimum rating (not applicable for OSM, but kept for interface consistency)

        Returns:
            List of business data dictionaries
        """
        # Map category to appropriate OSM amenity type
        category_map = {
            'hotel': 'tourism=hotel',
            'restaurant': 'amenity=restaurant',
            'bar': 'amenity=bar',
            'cafe': 'amenity=cafe',
            'bakery': 'shop=bakery',
            'nightclub': 'amenity=nightclub'
        }

        osm_category = category_map.get(category.lower(), f"amenity={category.lower()}")

        # First, get the bounding box for the location
        search_params = {
            'q': location,
            'format': 'json',
            'limit': 1
        }

        location_result = self._make_request('search', search_params)

        if not location_result or 'error' in location_result:
            logger.error(f"Location search failed for '{location}'")
            return []

        if not location_result:
            logger.error(f"No results found for location '{location}'")
            return []

        location_data = location_result[0]

        # Calculate bounding box based on radius
        # 1 degree of latitude is approximately 111 km
        lat = float(location_data['lat'])
        lon = float(location_data['lon'])

        # Convert radius to degrees (approximate)
        lat_offset = radius_km / 111.0
        lon_offset = radius_km / (111.0 * math.cos(math.radians(lat)))

        bbox = f"{lon - lon_offset},{lat - lat_offset},{lon + lon_offset},{lat + lat_offset}"

        # Search for businesses within the bounding box
        overpass_url = "https://overpass-api.de/api/interpreter"
        overpass_query = f"""
        [out:json];
        node[{osm_category}]({lat - lat_offset},{lon - lon_offset},{lat + lat_offset},{lon + lon_offset});
        out body;
        """

        try:
            overpass_response = requests.post(overpass_url, data={"data": overpass_query})
            overpass_response.raise_for_status()
            results = overpass_response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error querying Overpass API: {e}")
            return []

        businesses = []

        for element in results.get('elements', []):
            if element.get('type') != 'node':
                continue

            tags = element.get('tags', {})

            # Skip if no name
            if 'name' not in tags:
                continue

            website = tags.get('website', '')
            phone = tags.get('phone', '')

            # Construct the address from available tags
            address_parts = []
            if 'addr:housenumber' in tags and 'addr:street' in tags:
                address_parts.append(f"{tags['addr:housenumber']} {tags['addr:street']}")
            elif 'addr:street' in tags:
                address_parts.append(tags['addr:street'])

            if 'addr:postcode' in tags:
                address_parts.append(tags['addr:postcode'])

            address = ", ".join(address_parts)

            business_data = {
                'Business Name': tags.get('name', ''),
                'Category': category.capitalize(),
                'Address': address,
                'City': tags.get('addr:city', location_data.get('display_name', '').split(',')[0]),
                'Country': tags.get('addr:country', location_data.get('display_name', '').split(',')[-1].strip()),
                'Phone Number': phone,
                'Email': tags.get('email', ''),
                'Website': website,
                'Google Rating': '',  # Not available in OSM
                'Number of Reviews': '',  # Not available in OSM
                'Latitude': element.get('lat', ''),
                'Longitude': element.get('lon', ''),
                'API Source': self.get_api_name()
            }

            # Try to extract email from website if available and not already present
            if website and not business_data['Email']:
                email = self.extract_email_from_website(website)
                if email:
                    business_data['Email'] = email

            businesses.append(business_data)

        return businesses


class YelpFusionAPI(BusinessDataAPI):
    """Yelp Fusion API implementation (free tier)"""

    def __init__(self, api_key: str):
        """
        Initialize with Yelp API key

        Args:
            api_key: Yelp Fusion API key
        """
        self.api_key = api_key
        self.base_url = "https://api.yelp.com/v3"
        self.request_count = 0
        self.last_request_time = 0

    def get_api_name(self) -> str:
        return "Yelp Fusion API"

    def _handle_rate_limit(self):
        """
        Manage request rate to avoid hitting API limits
        Yelp has a limit of 5,000 calls per day, approximately 3.5 per minute
        """
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < 0.3 and self.request_count > 0:
            time.sleep(0.3 - time_since_last_request)

        self.request_count += 1
        self.last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[Any, Any]:
        """
        Make a request to the Yelp Fusion API

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            JSON response as dictionary
        """
        self._handle_rate_limit()

        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json'
        }

        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making request to Yelp Fusion API: {e}")
            return {"error": str(e)}

    def search_businesses(self,
                          location: str,
                          category: str,
                          radius_km: int,
                          min_rating: float) -> List[Dict[Any, Any]]:
        """
        Search for businesses based on criteria

        Args:
            location: City or country to search in
            category: Type of business (Hotel, Restaurant, Bar, etc.)
            radius_km: Search radius in kilometers
            min_rating: Minimum rating

        Returns:
            List of business data dictionaries
        """
        # Convert km to meters for Yelp API
        radius_meters = radius_km * 1000
        if radius_meters > 40000:  # Yelp's maximum radius is 40000 meters
            radius_meters = 40000

        # Map category to appropriate Yelp category
        category_map = {
            'hotel': 'hotels',
            'restaurant': 'restaurants',
            'bar': 'bars',
            'cafe': 'cafes',
            'bakery': 'bakeries',
            'nightclub': 'nightlife'
        }

        yelp_category = category_map.get(category.lower(), category.lower())

        search_params = {
            'location': location,
            'categories': yelp_category,
            'radius': radius_meters,
            'limit': 50  # Maximum allowed by Yelp
        }

        search_result = self._make_request('businesses/search', search_params)

        if 'error' in search_result:
            logger.error(f"Yelp search failed: {search_result.get('error', {}).get('description', 'Unknown error')}")
            return []

        businesses = []

        for business in search_result.get('businesses', []):
            # Skip businesses with too low rating
            if business.get('rating', 0) < min_rating:
                continue

            # Get business details
            business_id = business.get('id')
            if not business_id:
                continue

            details_result = self._make_request(f'businesses/{business_id}')

            if 'error' in details_result:
                logger.warning(f"Failed to get details for business {business.get('name')}")
                continue

            # Extract location components
            location_data = business.get('location', {})
            address = ', '.join(location_data.get('display_address', []))

            business_data = {
                'Business Name': business.get('name', ''),
                'Category': category.capitalize(),
                'Address': address,
                'City': location_data.get('city', ''),
                'Country': location_data.get('country', ''),
                'Phone Number': business.get('phone', ''),
                'Email': '',  # Yelp API doesn't provide email
                'Website': business.get('url', ''),
                'Google Rating': str(business.get('rating', '')),  # Yelp rating as a proxy
                'Number of Reviews': str(business.get('review_count', '')),
                'Latitude': business.get('coordinates', {}).get('latitude', ''),
                'Longitude': business.get('coordinates', {}).get('longitude', ''),
                'API Source': self.get_api_name()
            }

            # Try to extract email from website if available
            if business_data['Website']:
                email = self.extract_email_from_website(business_data['Website'])
                if email:
                    business_data['Email'] = email

            businesses.append(business_data)

            # Handle pagination if available
            offset = search_result.get('offset', 0) + len(search_result.get('businesses', []))
            total = search_result.get('total', 0)

            if offset < total and offset < 1000:  # Yelp's max is 1000 results
                search_params['offset'] = offset
                next_result = self._make_request('businesses/search', search_params)

                if 'error' not in next_result:
                    search_result = next_result
                else:
                    break

        return businesses




logger = logging.getLogger(__name__)




def filter_and_transform_businesses(businesses):
    """
    1) Keep only 'Business Name', 'Category', 'City', 'Phone Number', 'Website', and 'Email' fields.
    2) Skip the record if 'Phone Number', 'Website', and 'Email' are all empty,
       i.e., we only keep records that have at least one form of contact info.
    """
    filtered_list = []
    for biz in businesses:
        # Extract the required fields
        transformed = {
            'Business Name': biz.get('Business Name', '').strip(),
            'Category': biz.get('Category', '').strip(),
            'City': biz.get('City', '').strip(),
            'Phone Number': biz.get('Phone Number', '').strip(),
            'Website': biz.get('Website', '').strip(),
            'Email': biz.get('Email', '').strip(),
        }

        # If phone, website, and email are all empty, skip this record
        if not (transformed['Phone Number'] or
                transformed['Website'] or
                transformed['Email']):
            continue

        filtered_list.append(transformed)

    return filtered_list


def save_to_csv(businesses, output_file):
    """
    Filters out records that lack phone, website, and email (all empty)
    and saves the following columns to the CSV file:
    'Business Name', 'Category', 'City', 'Phone Number', 'Website', 'Email'.
    """
    # Filter/transform data
    processed_data = filter_and_transform_businesses(businesses)

    if not processed_data:
        logger.warning("No businesses to save after filtering.")
        return

    fieldnames = [
        'Business Name',
        'Category',
        'City',
        'Phone Number',
        'Website',
        'Email'
    ]

    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(processed_data)

        logger.info(f"Successfully saved {len(processed_data)} businesses to {output_file}")
    except Exception as e:
        logger.error(f"Error saving to CSV: {e}")





def filter_duplicate_businesses(businesses: List[Dict[Any, Any]]) -> List[Dict[Any, Any]]:
    """
    Remove duplicate businesses based on name and address

    Args:
        businesses: List of business data dictionaries

    Returns:
        Filtered list of businesses
    """
    unique_businesses = {}

    for business in businesses:
        # Create a key based on name and address
        key = f"{business['Business Name']}|{business['Address']}".lower()

        # If this is a new business or has more info than a previous entry, keep it
        if key not in unique_businesses or _business_has_more_info(business, unique_businesses[key]):
            unique_businesses[key] = business

    return list(unique_businesses.values())


def _business_has_more_info(new_business: Dict[Any, Any], existing_business: Dict[Any, Any]) -> bool:
    """
    Check if new business entry has more information than existing one

    Args:
        new_business: New business data
        existing_business: Existing business data

    Returns:
        True if new business has more info, False otherwise
    """
    # Count non-empty fields
    new_count = sum(1 for v in new_business.values() if v)
    existing_count = sum(1 for v in existing_business.values() if v)

    # Prioritize entries with email
    if new_business['Email'] and not existing_business['Email']:
        return True

    # Prioritize entries with phone
    if new_business['Phone Number'] and not existing_business['Phone Number']:
        return True

    # Prioritize Google Places API over others
    if new_business['API Source'] == 'Google Places API' and existing_business['API Source'] != 'Google Places API':
        return True

    # Otherwise, choose the one with more information
    return new_count > existing_count


def get_italian_cities():
    """Return a list of major Italian cities"""
    return [
        "Rome", "Milan", "Naples", "Turin", "Palermo", "Genoa", "Bologna",
        "Florence", "Bari", "Catania", "Venice", "Verona", "Messina", "Padua",
        "Trieste", "Brescia", "Parma", "Taranto", "Prato", "Modena", "Reggio Calabria",
        "Cagliari", "Livorno", "Perugia", "Foggia", "Siracusa", "Pescara", "Salerno",
        "Monza", "Bergamo", "Rimini", "Ferrara", "Sassari", "Como", "Lucca",
        "Ravenna", "Lecce", "Vicenza", "Treviso", "Pisa", "marche", "Brindisi", "Asti",
        "Mantua", "Massa", "Alessandria", "Savona", "Aosta", "Imperia", "Trento",
        "Udine", "Bolzano", "Novara", "Piacenza", "Ancona", "Arezzo", "Pesaro",
    ]


def prompt_user_input():
    """Interactive mode to get user inputs"""
    print("\n==== Hospitality Business Contact Finder ====")
    print("Focus: Italian Hospitality Businesses\n")

    # Location selection in Italy
    print("Select location in Italy:")
    italian_cities = get_italian_cities()
    for i, city in enumerate(italian_cities, 1):
        print(f"{i}. {city}")
    print(f"{len(italian_cities) + 1}. All of Italy")
    print(f"{len(italian_cities) + 2}. Custom location in Italy")

    location_choice = int(input("\nEnter number for location: "))

    if location_choice <= len(italian_cities):
        location = f"{italian_cities[location_choice - 1]}, Italy"
    elif location_choice == len(italian_cities) + 1:
        location = "Italy"
    else:
        custom_city = input("Enter custom location in Italy: ")
        location = f"{custom_city}, Italy"

    # Category selection
    print("\nSelect business category:")
    categories = ['hotel', 'restaurant', 'bar', 'cafe', 'bakery', 'nightclub', 'all']
    for i, category in enumerate(categories, 1):
        print(f"{i}. {category.capitalize()}")

    category_choice = int(input("\nEnter number for category: "))
    category = categories[category_choice - 1]

    # Radius
    radius = int(input("\nEnter search radius in kilometers (default 5): ") or "5")

    min_rating = float(input("\nEnter minimum rating (1.0-5.0, default 3.5): ") or "3.5")

    # Output file
    default_output = f"italian_{category}_businesses.csv"
    output = input(f"\nEnter output file name (default: {default_output}): ") or default_output

    # User selects the api source
    print("\nSelect API source:")
    print("1. Google Places API (premium data, requires API key)")
    print("2. Yelp Fusion API (free tier, requires API key)")
    print("3. OpenStreetMap API (completely free, no API key required)")

    api_choice = int(input("\nEnter number for API: "))

    api = None
    if api_choice == 1:
        api_key = input("Enter your Google Places API key: ")
        api = GooglePlacesAPI(api_key)
    elif api_choice == 2:
        api_key = input("Enter your Yelp Fusion API key: ")
        api = YelpFusionAPI(api_key)
    else:
        api = OpenStreetMapAPI()

    return {
        'location': location,
        'category': category,
        'radius': radius,
        'min_rating': min_rating,
        'output': output,
        'api': api
    }


# the main function works like a controller in MVC architecture
# it calls the prompt_user_input function to get user inputs
# and then calls the search_businesses function to search for businesses based on the user inputs
def main():
    """Main function to run the business finder"""
    # Ask user whether to use command-line args or interactive mode
    if len(sys.argv) > 1:
        mode_choice = input("Run in automatic mode with command-line arguments? (Y/n): ").lower() or "y"
        interactive_mode = mode_choice != "y"
    else:
        interactive_mode = True

    if interactive_mode:
        # Use interactive mode
        user_inputs = prompt_user_input()
        location = user_inputs['location']
        category = user_inputs['category']
        radius = user_inputs['radius']
        min_rating = user_inputs['min_rating']
        output = user_inputs['output']
        api = user_inputs['api']
    else:
        # Use command-line arguments
        parser = argparse.ArgumentParser(description='Find hospitality business contact information')

        parser.add_argument('--location', default='Italy', help='City or country to search in')
        parser.add_argument('--category', required=True,
                            choices=['hotel', 'restaurant', 'bar', 'cafe', 'bakery', 'nightclub', 'all'],
                            help='Type of business to search for')
        parser.add_argument('--radius', type=int, default=5, help='Search radius in kilometers')
        parser.add_argument('--min-rating', type=float, default=3.5, help='Minimum rating threshold')
        parser.add_argument('--output', default='italian_hospitality_businesses.csv', help='Output CSV file path')

        api_group = parser.add_mutually_exclusive_group(required=True)
        api_group.add_argument('--google-api-key', help='Google Places API key')
        api_group.add_argument('--yelp-api-key', help='Yelp Fusion API key')
        api_group.add_argument('--use-osm', action='store_true', help='Use OpenStreetMap API (free)')

        args = parser.parse_args()

        # Initialize the appropriate API
        location = args.location
        category = args.category
        radius = args.radius
        min_rating = args.min_rating
        output = args.output

        if args.google_api_key:
            api = GooglePlacesAPI(args.google_api_key)
        elif args.yelp_api_key:
            api = YelpFusionAPI(args.yelp_api_key)
        elif args.use_osm:
            api = OpenStreetMapAPI()

    # Set up categories to search
    categories = []
    if category == 'all':
        categories = ['hotel', 'restaurant', 'bar', 'cafe', 'bakery', 'nightclub']
    else:
        categories = [category]

    # Search for businesses in each category
    all_businesses = []

    for cat in categories:
        logger.info(f"Searching for {cat} businesses in {location} with {api.get_api_name()}")
        businesses = api.search_businesses(
            location=location,
            category=cat,
            radius_km=radius,
            min_rating=min_rating
        )

        logger.info(f"Found {len(businesses)} {cat} businesses")
        all_businesses.extend(businesses)

    # Remove duplicates
    logger.info(f"Filtering {len(all_businesses)} total businesses for duplicates")
    filtered_businesses = filter_duplicate_businesses(all_businesses)
    logger.info(f"Reduced to {len(filtered_businesses)} unique businesses")

    # Save results to CSV
    save_to_csv(filtered_businesses, output)
    logger.info(f"Results saved4 to {output}")


if __name__ == "__main__":
    main()
