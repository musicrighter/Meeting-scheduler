import nose
from main import *

def test_freeTimes():
#Test our get free times function with an arbitrary busy times obj
#This assures we can expect the same algorithmic outcome from any busy times
    testBusy = [{'start': '2015-11-09T09:30:00Z', 'end': '2015-11-09T16:30:00Z'}, {'start': '2015-11-11T14:00:00Z', 'end': '2015-11-11T22:30:00Z'}, {'start': '2015-11-12T09:00:00Z', 'end': '2015-11-12T10:30:00Z'}]
    assert (getFreeTime(testBusy))

def test_emptyCal():
#Incase there are no schedule conflicts and we have no busy times
    testBusy = [{}]
    assert (getFreeTime(testBusy))

def test_fullCal():
#Case where our calendar is completely full for range: 11/01/2015 - 11/07/2015
    testBusy = [{'start': '2015-11-01T00:00:00Z', 'end': '2015-11-07T11:45:00Z'}]
    assert (getFreeTime(testBusy))

def test_dateRange():
#Make sure our beginning date comes before our ending date for our date range
    assert (arrow.get(flask.session['begin_date']).timestamp() < arrow.get(flask.session['end_date']).timestamp())

def test_timeIntervals():
#To make sure we get the correct number of time intervals (intervals of 15 min) from our set range
    #This should have ten 15 min intervals
    testBusy = [{'start': '2015-11-01T10:00:00Z', 'end': '2015-11-07T12:30:00Z'}]
    assert ((arrow.get(flask.session['end_date']).timestamp() - arrow.get(flask.session['begin_date']).timestamp()) % 900 == getFreeTime(testBusy))

def test_busyResponse1():
#Test the response we get from google for our freebusy query
#Make sure we get an expected number of busy times back, for same times = 0
    testcalService = get_cal_service(flask.session['credentials'])
    testFBQ = { "timeMin" : "2015-11-01T00:00:00Z", "timeMax" : "2015-11-01T00:00:00Z", items: [{ "id" : "test" }] }
    testRecords = testcalService.freebusy().query(body = testFBQ).execute()
    assert (len(testRecords.get("calendars", {}).get(item, {}).get("busy"))) == 0)

def test_busyResponse2():
#Test the response we get from google for our freebusy query
#Make sure we get an expected number of busy times back, 1 day => no more than 60 x 60 x 24 seconds/times
    testcalService = get_cal_service(flask.session['credentials'])
    testFBQ = { "timeMin" : "2015-11-01T00:00:00Z", "timeMax" : "2015-11-02T00:00:00Z", items: [{ "id" : "test" }] }
    testRecords = testcalService.freebusy().query(body = testFBQ).execute()
    assert (len(testRecords.get("calendars", {}).get(item, {}).get("busy"))) <= (60 * 60 * 24))

def test_busyStart():
#Test the response we get from google for our freebusy query
#busy times cannot occur sooner than start of daterange
    testcalService = get_cal_service(flask.session['credentials'])
    testFBQ = { "timeMin" : "2015-11-01T00:00:00Z", "timeMax" : "2015-11-02T00:00:00Z", items: [{ "id" : "test" }] }
    testRecords = testcalService.freebusy().query(body = testFBQ).execute()
    assert (arrow.get(testRecords.get("calendars", {}).get(item, {}).get("busy"))[0]).timestamp() >= arrow.get("2015-11-01T00:00:00Z").timestamp())

def test_busyEnd():
#Test the response we get from google for our freebusy query
#busy times cannot occur after the end of daterange
    testcalService = get_cal_service(flask.session['credentials'])
    testFBQ = { "timeMin" : "2015-11-01T00:00:00Z", "timeMax" : "2015-11-02T00:00:00Z", items: [{ "id" : "test" }] }
    testRecords = testcalService.freebusy().query(body = testFBQ).execute()
    assert (arrow.get(testRecords.get("calendars", {}).get(item, {}).get("busy"))[len(testRecords.get("calendars", {}).get(item, {}).get("busy"))) - 1]).timestamp() <= arrow.get("2015-11-02T00:00:00Z").timestamp())

def test_errorRange():
#Test the response we get from google for our freebusy query
#check if we get expected error from google by sending a starting date that is after the ending date
    testcalService = get_cal_service(flask.session['credentials'])
    testFBQ = { "timeMin" : "2015-11-02T00:00:00Z", "timeMax" : "2015-11-01T00:00:00Z", items: [{ "id" : "test" }] }
    assert(!testcalService.freebusy().query(body = testFBQ))
