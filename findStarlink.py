from skyfield import almanac
from skyfield.api import Topos, load, N, W, wgs84
from skyfield.framelib import ecliptic_frame
from datetime import datetime, timedelta
from pytz import timezone
from math import sin, cos, radians, log10, pi
from concurrent.futures import ThreadPoolExecutor
import json
import requests

# Flags for debugging
DEBUG = False #True to print info
WEB = True    #False to work on a local file and avoid API calls to CELESTRAK. True to download the latest TLE file

# TLE data sources for Starlink satellites
starlink_url = 'http://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink&FORMAT=tle'
tle_file = "starlink_sat.txt"
   
# Load timescale
ts = load.timescale()

# Start and end time
start_time = ts.now()
end_time = ts.utc(start_time.utc.year, start_time.utc.month, start_time.utc.day + 4)

# Load almanac
eph = load('de421.bsp')

# Get the Sun and satellite positions
sun, earth,  = eph['sun'], eph['earth']

# Set observer's location (replace with your coordinates)
my_location = Topos(latitude_degrees=48.8534, longitude_degrees=2.3488)
tz = timezone('Europe/Paris')
bluffton = wgs84.latlon(48.8534 * N, 2.3488 * W)
observer = eph['earth'] + bluffton

# Load TLE data for Starlink satellites
def load_sat_data(url):
    if WEB:
        if DEBUG:
            print("Downloading data from Celestrak")
        response = requests.get(starlink_url)
        with open(tle_file, "wb") as f:
            f.write(response.content)

    sat_data = load.tle_file(tle_file)
    return sat_data

# Select the first satellite NORAD ID from the train
def one_sat_per_train():
    # Read the content of the text file
    with open(tle_file) as file:
        lines = file.readlines()

    # Initialize a dictionary to store the first Sat_ID for each Launch_ID
    launch_to_sat = {}

    # Iterate through each line
    for line in lines:
        # Check if the line starts with "1"
        if line.startswith("1"):
            # Extract Sat_ID and Launch_ID using string slicing
            sat_id = line[2:7].strip()
            launch_id = line[9:14].strip()
            # Store the first Sat_ID for each Launch_ID
            if launch_id not in launch_to_sat:
                launch_to_sat[launch_id] = sat_id

    # Print the first Sat_ID for each Launch_ID
    sat_train = []
    for launch_id, sat_id in launch_to_sat.items():
        sat_train.append(int(sat_id))

    return sat_train
        

# Convert degrees to compass direction
def azimuth_to_compass(azi):
    # Define the compass directions
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    # Convert the azimuth to an index
    index = round(azi / 22.5)
    # Use modulo operator to handle cases where index is 16
    index = index % 16
    # Return the compass direction
    return directions[index]
    
# Sort data by date and mag    
def sort_and_print(array):
    array.sort(key=lambda x: (x["date"], x["mag"]))
    
    # Initialize variables
    lowest_mag_per_day = {}
    for d in starlink_found:
        # If the date is not in lowest_mag_per_day or if the current mag is lower than the lowest mag for the date
        if d["date"] not in lowest_mag_per_day or d["mag"] < lowest_mag_per_day[d["date"]]["mag"]:
            lowest_mag_per_day[d["date"]] = d
    
    # Print the elements with the lowest mag per day
    result = []
    for date, element in lowest_mag_per_day.items():
        result.append(element)
    print(json.dumps(result, indent=4, default=str))    

    
# Take a satellite name and return its visibility information
def search_satellites(name):
    # Iterate over each satellite
        sat=by_number[name]	        
        t, events = sat.find_events(my_location, start_time, end_time, altitude_degrees=10.0)
        for t_sat_r, event in zip(t, events):
            
                if not (event == 0 and sat.at(t_sat_r).is_sunlit(eph)):  # 0 = satellite rises above altitude_degrees and is sunlit
                    continue
                
                t_sat_rise = t_sat_r.astimezone(tz)   
                
                # Set sun rising and setting times
                start_day = ts.utc(t_sat_r.utc.year, t_sat_r.utc.month, t_sat_r.utc.day, 0, 0, 0)
                end_day = ts.utc(t_sat_r.utc.year, t_sat_r.utc.month, t_sat_r.utc.day, 23, 59, 59)

                t_sun_s, event_sun = almanac.find_settings(observer, sun, start_day, end_day)
                t_sunset = t_sun_s[0].astimezone(tz)
                
                t_sun_r, event_sun_r = almanac.find_risings(observer, sun, start_day + 1 , end_day + 1)
                t_sunrise = t_sun_r[0].astimezone(tz)
                
                # Check if it's dark enough 
                if not(t_sat_rise > t_sunset + timedelta(minutes=15)):
                   continue
                
                # Set satellite culmination time within 10 min after rising
                times_c, events_c = sat.find_events(my_location, t_sat_r, t_sat_r + 0.007, altitude_degrees=10.0)
                for t_sat_c, event_sat_c in zip(times_c, events_c):
                    if event_sat_c == 1:
                       t_sat_culm = t_sat_c
                                                  
                # Set satellite setting time within 10 min after rising
                times_s, events_s = sat.find_events(my_location, t_sat_r, t_sat_r + 0.007, altitude_degrees=10.0)
                for t_sat_s, event_sat_s in zip(times_s, events_s):
                    if event_sat_s == 2:
                       t_sat_set = t_sat_s.astimezone(tz)
                
                pass_duration = t_sat_set - t_sat_rise
                
                # Check is satellite is visible long enough at night.
                if t_sat_rise < (t_sunrise - timedelta(hours=4)) and pass_duration > timedelta(minutes=3):
                    
                    if DEBUG:
                        
                       print("satellite_ID:", name, "t_sunset: ", str(t_sunset)[:16],", t_sunrise: ", str(t_sunrise)[:16], "t_sat_rise:", str(t_sat_rise)[:16], "t_sat_set:", str(t_sat_set)[:16], "pass_duration:", str(pass_duration)[:7])

                    # Calculate the apparent magnitude at culmination
                    # Ref: http://export.arxiv.org/pdf/2401.01546		                        
                    sat_phase_angle = earth.at(t_sat_culm).observe(earth + sat).apparent().phase_angle(sun)
                    sat_phi = sat_phase_angle.degrees
                    apparent_mag = 6.657 - 0.05474 * sat_phi + 0.001438 * sat_phi * sat_phi - 0.000008061 * sat_phi * sat_phi * sat_phi

                    # Adjust apparent magnitude for new VisoSat satellites which are 30% dimmer. Launched after 2021.11                         
                    if sat.model.satnum < 49752:
                        apparent_mag = apparent_mag - 1.3
                        
                    if DEBUG:                            
                       print("sat_phi:", round(sat_phi,0), ", mag:",round(apparent_mag,1))

                    # Select only satellites with enough brightness
                    if apparent_mag < 5.5:

                       # Calculate the start/end azimuth of the trajectory
                       difference = sat - my_location
                       topocentric = difference.at(t_sat_r)
                       sat_distance = topocentric.distance().km
                                                                       
                       start_azi = topocentric.altaz()[1].degrees
                       end_azi = start_azi + 180
                       
                       mag = round(apparent_mag,1)

                       data = {
                            "satellite": sat.name,
                            "risingTime": t_sat_rise.strftime('%d %b %Y, %H:%M'),
                            "culminationTime": t_sat_culm.astimezone(tz).strftime('%d %b %Y, %H:%M'),
                            "settingTime": t_sat_set.strftime('%d %b %Y, %H:%M'),
                            "startAz": azimuth_to_compass(start_azi),
                            "endAz": azimuth_to_compass(end_azi),
                            "mag": mag,
                            "date": t_sat_rise.strftime('%Y-%m-%d')
                        }
                            
                       starlink_found.append(data)
                    else:
                        continue

def main():    

    if DEBUG:
        # Printing start time
        print("Start Time: ", start_time.astimezone(tz).strftime('%d %b %Y, %H:%M'))
        print("Selected Starlink_IDs:",STARLINK_IDS)
        
    # Finding satellites
    with ThreadPoolExecutor(max_workers=8) as executor:
       for name in STARLINK_IDS:
           future = executor.submit(search_satellites, name)
           # Wait for the future to complete and retrieve its result
           sat_visibility_data = future.result()
    
    # Print results                 
    sort_and_print(starlink_found)
    
    if DEBUG:
        # Record the end time
        end_exec_time = ts.now()
    
        # Calculate the duration
        duration = datetime.strptime(end_exec_time.utc_iso(), "%Y-%m-%dT%H:%M:%SZ") - datetime.strptime(start_time.utc_iso(), "%Y-%m-%dT%H:%M:%SZ")
        # Print the duration in seconds
        print("\nStart Time: ", start_time.astimezone(tz).strftime('%d %b %Y, %H:%M:%S'), "\n  End Time: ", end_exec_time.astimezone(tz).strftime('%d %b %Y, %H:%M:%S'), "\n  Duration: ", duration)
        

# Init the array of the Starlink Trains
satellites = load_sat_data(starlink_url)
by_number = {sat.model.satnum: sat for sat in satellites}  
STARLINK_IDS = one_sat_per_train()
starlink_found = []

main()
