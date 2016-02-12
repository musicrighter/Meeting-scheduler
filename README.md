# proj6-Gcal
Snarf appointment data from a selection of a user's Google calendars 

This program connectes to a prespecified google calendar client and displays the 'busy' times for whichever set of calendars the user chooses.

#NOTES:
First a range set must be chosen
	-there is no date format error handling
	- format is strictly: MM/DD/YYYY - MM/DD/YYYY

Second you choose from a list of the client's calendars to display times

The main parts of the program I modified for the project were the '/choose' route in main.py and some of the html body as well as some javascript to handle the request. I used JSON to send the selected calendars to the server to request a list of busy dates from the google API and return the list.
