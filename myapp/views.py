import requests
import os
import math
from django.shortcuts import render
from rest_framework.decorators import api_view
from django.http import JsonResponse
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import ItemsSerializer
from datetime import datetime



def home(request):
    return HttpResponse("Hello, World!")



class ItemsView(APIView):
    # Constants for trip rules
    DAILY_DRIVING_LIMIT = 11  # 11 hours max driving per day
    REST_BREAK_TIME = 0.5  # 30 minutes rest break after 8 hours of driving
    LIFECYCLE_LIMIT = 70  # 70 hours max over 8 days
    FUELING_LENGTH = 1000
    FUELING_TIME_PER_MILES = 0.5  # 30 minutes per 1000 miles
    PICKUP_DROPOFF_TIME = 1  # 1 hour for picking up or dropping off
    
    def post(self, request):
        serializer = ItemsSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Extract data from the serializer
        current_location = serializer.validated_data['currentLocation']
        pickup_location = serializer.validated_data['pickupLocation']
        dropoff_location = serializer.validated_data['dropoffLocation']
        lifecycle_used = serializer.validated_data['lifeCycleUsed']

        # Get access token for Mapbox API
        access_token = os.getenv('ACCESS_TOKEN')
        direction_api_url = "https://api.mapbox.com/directions/v5/mapbox/driving"

        # Call Mapbox API to get directions ,geometry and rest posts
        response = self.get_directions(direction_api_url, current_location, pickup_location, dropoff_location, access_token)
        if response.status_code != 200:
            return Response({"error": "Error fetching data from Mapbox API"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Process the API response
        data = response.json()
        geometry = data['routes'][0]['geometry']
        distances_durations = self.extract_distances_durations(data)

        # Calculate times and distances
        times_distances = self.calculate_trip_info(distances_durations)


        # Calculate trip logs
        logs, day_count = self.generate_trip_logs(times_distances, lifecycle_used)

        # Get current date for the response
        current_date = datetime.now()



        return Response({
            'year': current_date.year,
            'month': current_date.month,
            'day': current_date.day,
            'logs_by_daily': self.organize_logs_by_day(logs, day_count),
            'geometry': geometry,
            **times_distances,
            'day_count': day_count
        }, status=status.HTTP_201_CREATED)

    def get_directions(self, direction_api_url, current_location, pickup_location, dropoff_location, access_token):
        """
        Call the Mapbox Directions API with the provided locations and return the response.
        """
        url = f"{direction_api_url}/{current_location['x']},{current_location['y']};{pickup_location['x']},{pickup_location['y']};{dropoff_location['x']},{dropoff_location['y']}?geometries=geojson&access_token={access_token}"
        return requests.get(url)
    
    def extract_distances_durations(self, data):
        """
        Extract the necessary distance and duration information from the API response.
        """
        routes = data['routes'][0]['legs']
        pickup_distance = routes[0]['distance']
        pickup_duration = routes[0]['duration']
        dropoff_distance = routes[1]['distance']
        dropoff_duration = routes[1]['duration']
        
        total_distance = data['routes'][0]['distance']
        total_duration = data['routes'][0]['duration']
        
        return {
            'pickup_distance': pickup_distance,
            'pickup_duration': pickup_duration,
            'dropoff_distance': dropoff_distance,
            'dropoff_duration': dropoff_duration,
            'total_distance': total_distance,
            'total_duration': total_duration
        }
    
    def calculate_trip_info(self, distances_durations):
     
        total_duration_hours = round(distances_durations['total_duration'] / 3600, 1)
        pickup_duration_hours = round(distances_durations['pickup_duration'] / 3600, 1)
        dropoff_duration_hours = round(distances_durations['dropoff_duration'] / 3600, 1)

        total_distance_miles = round(distances_durations['total_distance'] / 1609.34, 1)
        pickup_distance_miles = round(distances_durations['pickup_distance'] / 1609.34, 1)
        dropoff_distance_miles = round(distances_durations['dropoff_distance'] / 1609.34, 1)

        total_speed = round(total_distance_miles / total_duration_hours, 1)
        pickup_speed = round(pickup_distance_miles / pickup_duration_hours, 1)
        dropoff_speed = round(dropoff_distance_miles / dropoff_duration_hours, 1)

        return {
            'total_duration_hours': total_duration_hours,
            'pickup_duration_hours': pickup_duration_hours,
            'dropoff_duration_hours': dropoff_duration_hours,
            'total_distance_miles': total_distance_miles,
            'pickup_distance_miles': pickup_distance_miles,
            'dropoff_distance_miles': dropoff_distance_miles,
            'total_speed': total_speed,
            'pickup_speed': pickup_speed,
            'dropoff_speed': dropoff_speed
        }

    # for calculating  fueling distances and caring about main HOS regulations and  cycle used hours limitation
    def generate_trip_logs(self, times_distances, lifecycle_used):
        """
        Generate trip logs for the entire journey.
        """
        logs = []
        counter, counter_for_fuel, counter_for_limit, continue_drive_time = 0, 0, 0, 0
        actual_time, unit, day_count = 0, 0.1, 0
        actual_driving_time = 0
        current_speed = times_distances['pickup_speed']

        while round(counter, 1) <= times_distances['total_duration_hours']:
            if round(lifecycle_used + actual_driving_time) == self.LIFECYCLE_LIMIT:

                logs.append({
                    'event': "Driving",
                    'duration': round(continue_drive_time ,1),
                    'role': "Driving",
                    'actual_time': actual_time,
                    'day_count': day_count
                })
                actual_time += round(continue_drive_time ,1)
                logs.append({
                    'event': "LIFECYCLE_LIMIT",
                    'duration': 10,
                    'role': "DutyOff",
                    'actual_time': actual_time,
                    'day_count': day_count
                })
                
                actual_driving_time = 0
                actual_time += 10
                lifeCycleUsed = 0
                continue_drive_time = 0
            elif round(counter, 1) == times_distances['pickup_duration_hours']:

                logs.append({
                    'event': "Driving",
                    'duration': round(continue_drive_time ,1),
                    'role': "Driving",
                    'actual_time': actual_time,
                    'day_count': day_count
                })
                actual_time += round(continue_drive_time ,1)
                logs.append({
                    'event': "Picking Up",
                    'duration': self.PICKUP_DROPOFF_TIME,
                    'role': 'DutyOn',
                    'actual_time': actual_time,
                    'day_count': day_count
                })
                actual_time += self.PICKUP_DROPOFF_TIME
                continue_drive_time = 0
                current_speed = times_distances['dropoff_speed']
            elif round(counter, 1) == times_distances['total_duration_hours']:

                logs.append({
                    'event': "Driving",
                    'duration': round(continue_drive_time ,1),
                    'role': "Driving",
                    'actual_time': actual_time,
                    'day_count': day_count
                })

                actual_time += round(continue_drive_time ,1)

                logs.append({
                    'event': "Droping Off",
                    'duration': self.PICKUP_DROPOFF_TIME,
                    'role': 'DutyOn',
                    'actual_time': actual_time,
                    'day_count': day_count
                })
                actual_time += self.PICKUP_DROPOFF_TIME
                continue_drive_time = 0
            elif round(current_speed * counter_for_fuel) > self.FUELING_LENGTH:

                logs.append({
                    'event': "Driving",
                    'duration': round(continue_drive_time - 0.1 ,1),
                    'role': "Driving",
                    'actual_time': actual_time,
                    'day_count': day_count
                })

                actual_time += round(continue_drive_time - 0.1 ,1)

                logs.append({
                    'event': "Fueling",
                    'duration': self.FUELING_TIME_PER_MILES,
                    'role': 'DutyOn',
                    'actual_time': actual_time,
                    'day_count': day_count
                })

                actual_time += self.FUELING_TIME_PER_MILES
                counter_for_fuel = 0
                continue_drive_time = 0

            elif math.floor(continue_drive_time) == 8:

                logs.append({
                    'event': "Driving",
                    'duration': round(continue_drive_time - 0.1 , 1),
                    'role': "Driving",
                    'actual_time': actual_time,
                    'day_count': day_count
                })

                actual_time += round(continue_drive_time - 0.1 , 1)

                logs.append({
                    'event': "Resting 0.5-hour",
                    'duration': self.REST_BREAK_TIME,
                    'role': 'DutyOff',
                    'actual_time': actual_time,
                    'day_count': day_count
                })
                actual_time += self.REST_BREAK_TIME
                continue_drive_time = 0

            elif round(actual_time) < 24 and counter_for_limit > 11:

                logs.append({
                    'event': "Driving",
                    'duration': round(continue_drive_time ,1),
                    'role': "Driving",
                    'actual_time': actual_time,
                    'day_count': day_count
                })

                actual_time += round(continue_drive_time ,1)
                
                logs.append({
                    'event': "Sleeper Berth",
                    'duration': 24 - round(actual_time, 1),
                    'role': 'Sleeper Berth',
                    'actual_time': actual_time,
                    'day_count': day_count
                })

                day_count += 1
                counter_for_limit = 0
                # counter_for_fuel = 0
                actual_time = 0
                continue_drive_time = 0
        
       
            counter_for_limit += unit
            continue_drive_time += unit
            counter_for_fuel += unit
            actual_driving_time += unit
            counter += unit

        return logs, day_count

    def organize_logs_by_day(self, logs, day_count):
        """
        Organize the logs by day.
        """
        max_day_count = max(log['day_count'] for log in logs)
        logs_by_daily = [[] for _ in range(max_day_count + 1)]
        
        for log in logs:
            logs_by_daily[log['day_count']].append(log)
        
        return logs_by_daily