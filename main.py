import flask
from flask import render_template
from flask import request
from flask import url_for
from flask import jsonify
import uuid

import json
import logging

#Server for handling emails
import smtplib;
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Date handling 
import arrow # Replacement for datetime, based on moment.js
import datetime # But we still need time
from dateutil import tz  # For interpreting local times

# Mongo database
from pymongo import MongoClient
#from bson import ObjectId

import CONFIG

# OAuth2  - Google library implementation for convenience
from oauth2client import client
import httplib2   # used in oauth2 flow

# Google API for services 
from apiclient import discovery

#Establish our mongo database connection
try: 
    dbclient = MongoClient(CONFIG.MONGO_URL)
    db = dbclient.meetings
    collection = db.times

except:
    print("Failure opening database.  Is Mongo running? Correct password?")
    sys.exit(1)

###
# Globals
###
import CONFIG
app = flask.Flask(__name__)


SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = CONFIG.GOOGLE_LICENSE_KEY  ## You'll need this
APPLICATION_NAME = 'MeetMe class project'


#############################
#
#  Pages (routed from URLs)
#
#############################

@app.route("/")
@app.route("/index")
def index():
  app.logger.debug("Entering index")
  return render_template('index.html')

#The interface to allow the meeting proposer to establish a meeting
#It merges two lists of free times from both the proposer and participants who responded into a single list and renders the interface to choose one
@app.route("/setMeeting")
def setMeeting():

    #Variables for times 1, times 2, and mergedtimes = possible
    proposed = collection.find_one()['times']
    participate = flask.session['response']
    possible = []

    #Cycle through every available time for both proposer and participant and compare to find intersections to include in a list of free times
    for time in proposed:
        found = False
        for x in participate:
           if x == time:
               found = True
        if found:
            possible.append(time)

    flask.session['possibles'] = possible

    return render_template('setmeet.html')

#Delete the proposal by update the collection document to empty in the mongodb
@app.route("/delProposal")
def delProposal():
    delProp = { "id" : "meeting_proposal",
                         "times" : "" }
    collection.update({ "id" : "meeting_proposal" }, delProp)
    #Toggle delete button variable
    flask.session['propDeleted'] = True
    
    return flask.redirect(flask.url_for("setMeeting"))

#Much like the /choose method
#This similar method is called when the proposer sends a link to a meeting participant via email
#It allows the participant to intersect the proposed free times with their own
#It then triggers a response for the proposer to go back to index to choose a time that works
@app.route("/emailRouted")
def emailRouted():
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))
    
    #Flag variable for displaying the proposer or participants calendar selection screens in index
    flask.session['propCals'] = False

    #Get service object for google calendar api
    gcal_service = get_gcal_service(credentials)

    busy = [ ]
    #receive selected calendar id's from JSON request
    calsSelected = request.args.get('selected')
    
    #If defined, convert to iterable list
    if (calsSelected):
        cal = json.loads(calsSelected).get("cals", {})

        #for each calendar, send a new freebusyquery  
        #and add the results into the busy list
        for item in cal:
            
            freebusyquery = {
                             "timeMin" : flask.session['begin_date'],
                             "timeMax" : flask.session['end_date'],
                             "items": [{ "id" : item }]
                            }
    
            freebusyQuery = gcal_service.freebusy().query(body = freebusyquery)
        
            BUSY_RECORDS = freebusyQuery.execute()
            busy.append(BUSY_RECORDS.get("calendars", {}).get(item, {}).get("busy"))
        #Flag variables to use in index for displaying sections
        flask.session['responded'] = True
        flask.session['propCals'] = False
        
    #get free times using busy times
    free = getFreeTime(busy)

    #Declare variable to use in other functions
    flask.session['response'] = free

    #make our flask session calendar object
    flask.session['calendars'] = list_calendars(gcal_service)

    #After first reroute, simply reload screen
    if not busy:
        return flask.redirect(flask.url_for("index"))
    #or if we have our busy/free time object, return the request via JSON
    else:
        flask.session['propCals'] = True
        return jsonify(busyT=free)

@app.route("/choose")
def choose():
    ## **ADDED**
    ## This function also responds to a JSON request with a list of
    ## busy times for the calendars given and sends the list back
    ##
    ## We'll need authorization to list calendars 
    ## I wanted to put what follows into a function, but had
    ## to pull it back here because the redirect has to be a
    ## 'return' 
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))
   
    flask.session['propCals'] = False

    #Get service object for google calendar api
    gcal_service = get_gcal_service(credentials)

    busy = [ ]
    #receive selected calendar id's from JSON request
    calsSelected = request.args.get('selected')
    
    #If defined, convert to iterable list
    if (calsSelected):
        cal = json.loads(calsSelected).get("cals", {})

        #for each calendar, send a new freebusyquery  
        #and add the results into the busy list
        for item in cal:
            
            freebusyquery = {
                             "timeMin" : flask.session['begin_date'],
                             "timeMax" : flask.session['end_date'],
                             "items": [{ "id" : item }]
                            }
    
            freebusyQuery = gcal_service.freebusy().query(body = freebusyquery)
        
            BUSY_RECORDS = freebusyQuery.execute()
            busy.append(BUSY_RECORDS.get("calendars", {}).get(item, {}).get("busy"))

        flask.session['propCals'] = True

    free = getFreeTime(busy)

    ###ADD FREE TIMES TO DB HERE
    meeting_proposal = { "id" : "meeting_proposal",
                         "times" : free }

    #collection.insert(meeting_proposal)
    collection.update({ "id" : "meeting_proposal" }, meeting_proposal)

    #app.logger.debug("Returned from get_gcal_service")
    flask.session['calendars'] = list_calendars(gcal_service)
    
    #If no query is done/requested, return to index
    #else return the JSON request with busy list
    if not busy:
        return flask.redirect(flask.url_for("index"))
    else:
        return jsonify(busyT=free)

#attempt at automating email
@app.route("/email")
def email():
    email = request.args.get('mail')
    #key = request.args.get('free')
    
    msg = MIMEMultipart()
    msg['To'] = email
    msg['From'] = 'diligent.trev@gmail.com'
    msg['Subject'] = 'Meeting Proposal'
    message = 'test'
    msg.attach(MIMEText(message))

    smtpObj = smtplib.SMTP('smtp.gmail.com', 587)
    smtpObj.starttls()
    try:
        smtpObj.sendmail('diligent.trev@gmail.com', [email], msg.as_string())
    finally:
        smtpObj.quit()

    return flask.redirect(flask.url_for("index"))

####
#
#  Google calendar authorization:
#      Returns us to the main /choose screen after inserting
#      the calendar_service object in the session state.  May
#      redirect to OAuth server first, and may take multiple
#      trips through the oauth2 callback function.
#
#  Protocol for use ON EACH REQUEST: 
#     First, check for valid credentials
#     If we don't have valid credentials
#         Get credentials (jump to the oauth2 protocol)
#         (redirects back to /choose, this time with credentials)
#     If we do have valid credentials
#         Get the service object
#
#  The final result of successful authorization is a 'service'
#  object.  We use a 'service' object to actually retrieve data
#  from the Google services. Service objects are NOT serializable ---
#  we can't stash one in a cookie.  Instead, on each request we
#  get a fresh serivce object from our credentials, which are
#  serializable. 
#
#  Note that after authorization we always redirect to /choose;
#  If this is unsatisfactory, we'll need a session variable to use
#  as a 'continuation' or 'return address' to use instead. 
#
####

def valid_credentials():
    """
    Returns OAuth2 credentials if we have valid
    credentials in the session.  This is a 'truthy' value.
    Return None if we don't have credentials, or if they
    have expired or are otherwise invalid.  This is a 'falsy' value. 
    """
    if 'credentials' not in flask.session:
      return None

    credentials = client.OAuth2Credentials.from_json(
        flask.session['credentials'])

    if (credentials.invalid or
        credentials.access_token_expired):
      return None
    return credentials


def get_gcal_service(credentials):
  """
  We need a Google calendar 'service' object to obtain
  list of calendars, busy times, etc.  This requires
  authorization. If authorization is already in effect,
  we'll just return with the authorization. Otherwise,
  control flow will be interrupted by authorization, and we'll
  end up redirected back to /choose *without a service object*.
  Then the second call will succeed without additional authorization.
  """
  app.logger.debug("Entering get_gcal_service")
  http_auth = credentials.authorize(httplib2.Http())
  service = discovery.build('calendar', 'v3', http=http_auth)
  app.logger.debug("Returning service")
  return service

@app.route('/oauth2callback')
def oauth2callback():
  """
  The 'flow' has this one place to call back to.  We'll enter here
  more than once as steps in the flow are completed, and need to keep
  track of how far we've gotten. The first time we'll do the first
  step, the second time we'll skip the first step and do the second,
  and so on.
  """
  app.logger.debug("Entering oauth2callback")
  flow =  client.flow_from_clientsecrets(
      CLIENT_SECRET_FILE,
      scope= SCOPES,
      redirect_uri=flask.url_for('oauth2callback', _external=True))
  ## Note we are *not* redirecting above.  We are noting *where*
  ## we will redirect to, which is this function. 
  
  ## The *second* time we enter here, it's a callback 
  ## with 'code' set in the URL parameter.  If we don't
  ## see that, it must be the first time through, so we
  ## need to do step 1. 
  app.logger.debug("Got flow")
  if 'code' not in flask.request.args:
    app.logger.debug("Code not in flask.request.args")
    auth_uri = flow.step1_get_authorize_url()
    return flask.redirect(auth_uri)
    ## This will redirect back here, but the second time through
    ## we'll have the 'code' parameter set
  else:
    ## It's the second time through ... we can tell because
    ## we got the 'code' argument in the URL.
    app.logger.debug("Code was in flask.request.args")
    auth_code = flask.request.args.get('code')
    credentials = flow.step2_exchange(auth_code)
    flask.session['credentials'] = credentials.to_json()
    ## Now I can build the service and execute the query,
    ## but for the moment I'll just log it and go back to
    ## the main screen
    app.logger.debug("Got credentials")
    return flask.redirect(flask.url_for('choose'))

#####
#
#  Option setting:  Buttons or forms that add some
#     information into session state.  Don't do the
#     computation here; use of the information might
#     depend on what other information we have.
#   Setting an option sends us back to the main display
#      page, where we may put the new information to use. 
#
#####

@app.route('/setrange', methods=['POST'])
def setrange():
    """
    User chose a date range with the bootstrap daterange
    widget.
    """
    app.logger.debug("Entering setrange")  
    flask.flash("Setrange gave us '{}'".format(
      request.form.get('daterange')))
    daterange = request.form.get('daterange')
    flask.session['daterange'] = daterange
    daterange_parts = daterange.split()
    flask.session['begin_date'] = interpret_date(daterange_parts[0])
    flask.session['end_date'] = interpret_date(daterange_parts[2])
    app.logger.debug("Setrange parsed {} - {}  dates as {} - {}".format(
      daterange_parts[0], daterange_parts[1], 
      flask.session['begin_date'], flask.session['end_date']))
    return flask.redirect(flask.url_for("choose"))

####
#
#   Initialize session variables 
#
####

def init_session_values():
    """
    Start with some reasonable defaults for date and time ranges.
    Note this must be run in app context ... can't call from main. 
    """
    # Default date span = tomorrow to 1 week from now
    now = arrow.now('local')
    tomorrow = now.replace(days=+1)
    nextweek = now.replace(days=+7)
    flask.session["begin_date"] = tomorrow.floor('day').isoformat()
    flask.session["end_date"] = nextweek.ceil('day').isoformat()
    flask.session["daterange"] = "{} - {}".format(
        tomorrow.format("MM/DD/YYYY"),
        nextweek.format("MM/DD/YYYY"))
    # Default time span each day, 8 to 5
    flask.session["begin_time"] = interpret_time("9am")
    flask.session["end_time"] = interpret_time("5pm")

def interpret_time( text ):
    """
    Read time in a human-compatible format and
    interpret as ISO format with local timezone.
    May throw exception if time can't be interpreted. In that
    case it will also flash a message explaining accepted formats.
    """
    app.logger.debug("Decoding time '{}'".format(text))
    time_formats = ["ha", "h:mma",  "h:mm a", "H:mm"]
    try: 
        as_arrow = arrow.get(text, time_formats).replace(tzinfo=tz.tzlocal())
        app.logger.debug("Succeeded interpreting time")
    except:
        app.logger.debug("Failed to interpret time")
        flask.flash("Time '{}' didn't match accepted formats 13:30 or 1:30pm"
              .format(text))
        raise
    return as_arrow.isoformat()

def interpret_date( text ):
    """
    Convert text of date to ISO format used internally,
    with the local time zone.
    """
    try:
      as_arrow = arrow.get(text, "MM/DD/YYYY").replace(
          tzinfo=tz.tzlocal())
    except:
        flask.flash("Date '{}' didn't fit expected format 12/31/2001")
        raise
    return as_arrow.isoformat()

def next_day(isotext):
    """
    ISO date + 1 day (used in query to Google calendar)
    """
    as_arrow = arrow.get(isotext)
    return as_arrow.replace(days=+1).isoformat()

####
#
#  Functions (NOT pages) that return some information
#
####

def getFreeTime(busy):
    freeTime = [ ]
    busyFlag = [False] * (12)
    rangeStart = arrow.get(flask.session['begin_date']).timestamp
    rangeEnd = arrow.get(flask.session['end_date']).timestamp
    
    for x in range(rangeStart, rangeEnd):
        if (x % 900 == 0): #check intervals of 900 sec = 15 min
            for b in busy:
                for index, s in enumerate(b):
                    if ( x == arrow.get(b[index]['start']).timestamp ):
                        busyFlag[index] = True
                    if ( x == arrow.get(b[index]['end']).timestamp ):
                        busyFlag[index] = False

            free = True
            for c in busyFlag:
                if ( c == True ):
                    free = False
                    break

            if ( free == True ):
                freeTime.append(arrow.get(x).to('US/Pacific').format('MM-DD-YYYY HH:mm'))

    #Google calendar doesn't show 12:00am-5:00am, we remove those intervals
    freeTimeAdj = []
    for time in freeTime:
        if "00:" not in time and "01:" not in time and "02:" not in time and "03:" not in time and "04:" not in time:
            freeTimeAdj.append(time)

    return freeTimeAdj
  
def list_calendars(service):
    """
    Given a google 'service' object, return a list of
    calendars.  Each calendar is represented by a dict, so that
    it can be stored in the session object and converted to
    json for cookies. The returned list is sorted to have
    the primary calendar first, and selected (that is, displayed in
    Google Calendars web app) calendars before unselected calendars.
    """
    app.logger.debug("Entering list_calendars")  
    calendar_list = service.calendarList().list().execute()["items"]
    result = [ ]

    for cal in calendar_list:
        kind = cal["kind"]
        id = cal["id"]
        if "description" in cal: 
            desc = cal["description"]
        else:
            desc = "(no description)"
        summary = cal["summary"]
        # Optional binary attributes with False as default
	#****EXTEND to allow selection between calendars****
        selected = ("selected" in cal) and cal["selected"]
        primary = ("primary" in cal) and cal["primary"]
        
        result.append(
          { "kind": kind,
            "id": id,
            "summary": summary,
            "selected": selected,
            "primary": primary
            })
    return sorted(result, key=cal_sort_key)


def cal_sort_key( cal ):
    """
    Sort key for the list of calendars:  primary calendar first,
    then other selected calendars, then unselected calendars.
    (" " sorts before "X", and tuples are compared piecewise)
    """
    if cal["selected"]:
       selected_key = " "
    else:
       selected_key = "X"
    if cal["primary"]:
       primary_key = " "
    else:
       primary_key = "X"
    return (primary_key, selected_key, cal["summary"])
    
#################
#
# Functions used within the templates
#
#################

@app.template_filter( 'fmtdate' )
def format_arrow_date( date ):
    try: 
        normal = arrow.get( date )
        return normal.format("ddd MM/DD/YYYY")
    except:
        return "(bad date)"

@app.template_filter( 'fmttime' )
def format_arrow_time( time ):
    try:
        normal = arrow.get( time )
        return normal.format("HH:mm")
    except:
        return "(bad time)"
    
#############


if __name__ == "__main__":
  # App is created above so that it will
  # exist whether this is 'main' or not
  # (e.g., if we are running in a CGI script)

  app.secret_key = str(uuid.uuid4())  
  app.debug=CONFIG.DEBUG
  app.logger.setLevel(logging.DEBUG)
  # We run on localhost only if debugging,
  # otherwise accessible to world
  if CONFIG.DEBUG:
    # Reachable only from the same computer
    app.run(port=CONFIG.PORT)
  else:
    # Reachable from anywhere 
    app.run(port=CONFIG.PORT,host="0.0.0.0")
    
