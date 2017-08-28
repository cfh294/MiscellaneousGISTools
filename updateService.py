"""
updateService.py

This script updates ArcGIS Online feature services programmatically. Much of the base code in this script was
found at: https://blogs.esri.com/esri/arcgis/2013/04/23/updating-arcgis-com-hosted-feature-services-with-python/ .
Tweaks were made in August, 2017 by Connor Hornibrook.

Script can be run on the command line like so:
$usr> python updateService.py <service_name> <mxd_path>

Requirements:
- Python 2.7
- Two environment variables: ARCGIS_ONLINE_USER and ARCGIS_ONLINE_PASSWORD, set accordingly

"""
import os
import sys
import logging
from math import floor as round_down
from datetime import datetime as dt
from xml.dom import minidom
from arcpy import SignInToPortal_server, StageService_server, UploadServiceDefinition_server, ExecuteError
from arcpy.mapping import AnalyzeForSD, MapDocument, CreateMapSDDraft

# Constants
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(PROJECT_ROOT, "Logs")
if not os.path.isdir(LOG_DIR):
    os.mkdir(LOG_DIR)

LOG_DATE_FMT = "%Y-%m-%d %I:%M:%S %p"
ARCGIS_ONLINE_USER = os.environ["ARCGIS_ONLINE_USER"]
ARCGIS_ONLINE_PASSWORD = os.environ["ARCGIS_ONLINE_PASSWORD"]
MIN_ARGS = 3

if __name__ == "__main__":

    # start the timer
    start = dt.now()

    # trigger variable that is used to set the exit code
    exitStatus = 0

    # grab the script arguments
    numArgs = len(sys.argv)
    if numArgs != MIN_ARGS:
        print "Not enough arguments provided"
        sys.exit(1)
    serviceName = sys.argv[1]
    path2MXD = sys.argv[2]  # os.path.join(projectRoot, "testPoints.mxd")

    # a bunch of code for log setup
    dateString = start.strftime("%Y_%m_%d")
    logFmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt=LOG_DATE_FMT)
    logger = logging.getLogger("Update Service '{0}'".format(serviceName))
    logger.setLevel(logging.INFO)
    logHandler = logging.FileHandler(os.path.join(LOG_DIR, "{0}_{1}_serviceupdate.log".format(dateString, serviceName)),
                                     mode="w")
    logHandler.setFormatter(logFmt)
    logger.addHandler(logHandler)
    logger.info("Start\n")

    # Build paths that will be used for the temporary output sd files
    SDdraft = os.path.join(PROJECT_ROOT, "tempdraft.sddraft")
    newSDdraft = os.path.join(PROJECT_ROOT, "updatedDraft.sddraft")
    SD = os.path.join(PROJECT_ROOT, serviceName + ".sd")

    # login to ArcGIS Online using credentials found in system environment variables
    logger.info("Logging into ArcGIS Online")
    passwordLength = len(ARCGIS_ONLINE_PASSWORD)
    if passwordLength <= 1:
        passwordText = "*"
    else:
        passwordText = ARCGIS_ONLINE_PASSWORD[0] + ("*" * (passwordLength - 1))
    logger.info("User: {0}, Password: {1}".format(ARCGIS_ONLINE_USER, passwordText))

    try:
        SignInToPortal_server(ARCGIS_ONLINE_USER, ARCGIS_ONLINE_PASSWORD, "http://www.arcgis.com/")
    except ExecuteError:
        logger.setLevel(logging.ERROR)
        logger.error("Could not log into ArcGIS Online, check credential evn variables!")
        sys.exit(1)
    logger.info("Login successful\n")

    # grab the mxd file that was specified as the second script parameter, verify that it exists
    mxd = ""
    try:
        mxd = MapDocument(path2MXD)
    except AssertionError:
        logger.setLevel(logging.ERROR)
        logger.error("Invalid mxd path!")
        sys.exit(1)
    logger.info("Mxd path '{0}' is valid".format(path2MXD))

    # create the service definition draft file, using one of the paths that was parsed earlier
    logger.info("Creating SD draft file")
    CreateMapSDDraft(mxd, SDdraft, serviceName, "MY_HOSTED_SERVICES")  # , summary="test summary", tags="parcels")
    logger.info("'{0}' created".format(SDdraft))

    # Read the contents of the original SD Draft into an xml parser
    logger.info("Parsing XML")
    doc = minidom.parse(SDdraft)
    logger.info("XML parsed")

    # Comments and code between the separator lines are straight from the original code:
    ####################################################################################################################
    # The follow 5 code pieces modify the SDDraft from a new MapService
    # with caching capabilities to a FeatureService with Query,Create,
    # Update,Delete,Uploads,Editing capabilities. The first two code
    # pieces handle overwriting an existing service. The last three pieces
    # change Map to Feature Service, disable caching and set appropriate
    # capabilities. You can customize the capabilities by removing items.
    # Note you cannot disable Query from a Feature Service.

    tagsType = doc.getElementsByTagName("Type")
    for tagType in tagsType:
        if tagType.parentNode.tagName == "SVCManifest":
            if tagType.hasChildNodes():
                tagType.firstChild.data = "esriServiceDefinitionType_Replacement"

    tagsState = doc.getElementsByTagName("State")
    for tagState in tagsState:
        if tagState.parentNode.tagName == "SVCManifest":
            if tagState.hasChildNodes():
                tagState.firstChild.data = "esriSDState_Published"

    # Change service type from map service to feature service
    typeNames = doc.getElementsByTagName("TypeName")
    for typeName in typeNames:
        if typeName.firstChild.data == "MapServer":
            typeName.firstChild.data = "FeatureServer"

    # Turn off caching
    # print "Config"
    # configProps = doc.getElementsByTagName('ConfigurationProperties')[0]
    # propArray = configProps.firstChild
    # propSets = propArray.childNodes
    # for propSet in propSets:
    #     keyValues = propSet.childNodes
    #     for keyValue in keyValues:
    #         if keyValue.tagName == 'Key':
    #             if keyValue.firstChild.data == "isCached":
    #                 keyValue.nextSibling.firstChild.data = "false"

    # Turn on feature access capabilities
    # configProps = doc.getElementsByTagName('Info')[0]

    # print "Prop Array"
    # propArray = configProps.firstChild
    # propSets = propArray.childNodes
    # for propSet in propSets:
    #     keyValues = propSet.childNodes
    #     for keyValue in keyValues:
    #         if keyValue.tagName == 'Key':
    #             if keyValue.firstChild.data == "WebCapabilities":
    #                 keyValue.nextSibling.firstChild.data = "Query,Create,Update,Delete,Uploads,Editing"
    ####################################################################################################################

    # Write the new draft to disk
    logger.info("Creating new SD file")
    f = open(newSDdraft, "w")
    doc.writexml(f)
    f.close()
    logger.info("'{0}' created".format(newSDdraft))

    # Analyze the service to see if we can stage and upload changes
    logger.info("Analyzing SD file")
    analysis = AnalyzeForSD(newSDdraft)
    logger.info("SD file analysis complete\n")

    # if there are no errors, we can proceed to the staging/upload process
    if analysis["errors"] == {}:

        # Stage the service
        logger.info("Staging service server")
        try:
            StageService_server(newSDdraft, SD)
        except ExecuteError:
            logger.setLevel(logging.ERROR)
            logger.error("Staging failed!")
            sys.exit(1)
        logger.info("Staging complete")

        # The following block comment is from the original code:
        #
        # Upload the service. The OVERRIDE_DEFINITION parameter allows you to override the
        # sharing properties set in the service definition with new values. In this case,
        # the feature service will be shared to everyone on ArcGIS.com by specifying the
        # SHARE_ONLINE and PUBLIC parameters. Optionally you can share to specific groups
        # using the last parameter, in_groups.
        logger.info("Uploading service definition")
        try:
            UploadServiceDefinition_server(SD, "My Hosted Services", serviceName, "", "", "", "", "", "", "",
                                           "SHARE_ORGANIZATION", "")
        except ExecuteError:
            logger.setLevel(logging.ERROR)
            logger.error("Upload of service definition failed!")
            sys.exit(1)
        logger.info("Uploaded and overwrote service\n")

    # If the sddraft analysis contained errors, display them and quit.
    else:
        logger.setLevel(logging.ERROR)
        logger.error("Following errors detected: {0}".format(analysis["errors"]))
        exitStatus = 1

    # remove the temp service definition files
    os.remove(SDdraft)
    logger.info("'{0}' removed".format(SDdraft))
    os.remove(SD)
    logger.info("'{0}' removed\n".format(SD))

    # stop the timer and calculate minutes and seconds. finish the log file
    finish = dt.now()
    el = (finish - start).total_seconds()
    minutes, seconds = int(el // 60), int(round_down(el % 60))
    minutesText = "minutes" if minutes == 0 or minutes > 1 else "minute"
    secondsText = "seconds" if seconds == 0 or seconds > 1 else "second"
    logger.info("Finished. Elapsed time: {0} {1}, {2} {3}".format(minutes, minutesText, seconds, secondsText))

    # Exit the program with the correct status code. If errors were found earlier, a value of 1 will be passed to
    # sys.exit (signalling a finished run with errors), else a value of 0 will be passed (signalling a successful run)
    sys.exit(exitStatus)
