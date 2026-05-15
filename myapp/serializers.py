from rest_framework import serializers
from .models import Employee

class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ['name', 'age', 'department']

class PointSerializer(serializers.Serializer):
    x = serializers.FloatField()
    y = serializers.FloatField()        

class ItemsSerializer(serializers.Serializer):
        currentLocation = PointSerializer()
        pickupLocation = PointSerializer()
        dropoffLocation = PointSerializer()
        lifeCycleUsed = serializers.IntegerField()