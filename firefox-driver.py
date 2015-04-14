from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from urlparse import urlparse
import time
import requests
import logging
import sys
import json
import os
import subprocess
import psutil

####Configure Info######

logger = logging.getLogger('firefox-driver')

#########################################
#			Selenium Utilities			#
#########################################
def openNewTab(browser):
	ActionChains(browser).send_keys(Keys.COMMAND, "t").perform()
	ActionChains(browser).send_keys(Keys.COMMAND, "t").perform()

def closeCurrentTab(browser):
	browser.find_element_by_tag_name('body').send_keys(Keys.COMMAND + 'w')

def testSelenium():
	profile = webdriver.FirefoxProfile(FirefoxProfileName)
	browser = webdriver.Firefox(profile)

	openNewTab()
	browser.get('http://www.cnn.com/')
	closeCurrentTab()
	time.sleep(1)

	openNewTab()
	browser.get('http://www.yahoo.com/')
	browser.quit()
	logger.info("Done")

#########################################
#			Process Utilities			#
#########################################
def killProcessAndChildren(pid):
	parent = psutil.Process(pid)
	for child in parent.children(recursive=True):  # or parent.children() for recursive=False
		child.kill()
	parent.kill()

def runBackgroundProcess(args,outFile,errFile):
	try:
		p = subprocess.Popen(args,stdout=outFile,stderr=errFile)
		return p
	except Exception as e:
		logger.error("error runBackgroundProcess due to: %s" % str(e))

def runMitmproxy(scriptPath, firstURL, suspendURL, logDir, logFile, threshold):
	param = '"\"%s %s %s %s %s %d\""'%(scriptPath,firstURL,suspendURL,\
								logDir, logFile, threshold)
	args = ['mitmproxy','-s',param]
	outFileName = os.path.join(logDir, 'stdout.txt')
	outFile = open(outFileName,'w')
	errFileName = os.path.join(logDir,'stderr.txt')
	errFile = open(errFileName,'w')
	logger.debug("prepare to run mitmproxy %s"%(' '.join(args),))
	p = runBackgroundProcess(args, outFile, errFile)
	time.sleep(1)
	p.poll()
	if p.returncode == None:
		logger.debug("successfully run mitmproxy with pid %d "%p.pid)
		return p, outFile, errFile
	else:
		logger.error("failed to run mitmproxy")
		return None, None, None

def terminateMitmproxy(proxyProcess, outFile, errFile):
	try:
		outFile.close()
		errFile.close()
		killProcessAndChildren(proxyProcess.pid)
	except Exception as e:
		logger.error("failed to terminate mitmproxy "+str(e))


#########################################
#			Other Utilities				#
#########################################

def sendExitSignalToProxy(port=8080):
	proxies = {
		"http": "http://localhost:8080",
		"https": "http://localhost:8080",
	}
	url = "http://localhost/commands/exit"
	try:
		r = requests.get(url,timeout=5,proxies=proxies)
		if r.text.strip() == "done":
			logger.debug("command EXIT has been received")
	except Exception as e:
		logger.error("error "+str(e))

def readConfigure(file_path):
	try:
		json_file = open(file_path)
		data = json.load(json_file)
		json_file.close()
		return data
	except Exception as e:
	    logger.error("failed to parse configure file "+file_path+" "+str(e))
	    return None


#########################################
#			Other Utilities				#
#########################################

def repeatedVisitWebPage(url,times,configureFilePath,logFileBaseName=None):
	logger.debug("Start visiting web page %s for %d times..."%(url,times))
	data = readConfigure(configureFilePath)
	if data == None:
		logger.error("failed to read configure file")
		return

	profile = webdriver.FirefoxProfile(data['firefoxProfilePath'])
	browser = webdriver.Firefox(profile)
	if browser == None:
		logger.error("failed to create firefox instance")
		return 
	o = urlparse(url)
	host = o.netloc;
	if logFileBaseName == None:
		logFileBaseName = host+'_%d'
	else:
		logFileBaseName += '_%d'
	for i in range(times):
		try:
			logName = logFileBaseName % i
			logger.debug("  start running mitmproxy");
			p, outFile, errFile = runMitmproxy(data['mitmproxyScriptPath'], \
									url, "none", data['logDir'], logName, 10)
			logger.debug("  start browsing %d time and store to file %s"%(i,logName) )
			openNewTab(browser)
			browser.get(url)
			closeCurrentTab(browser)
			logger.debug("  done browsing %d time and store to file %s"%(i,logName) )
			sendExitSignalToProxy()
			terminateMitmproxy(p, outFile, errFile)
			logger.debug("  done terminating mitmproxy")
			time.sleep(2);
		except Exception as e:
			logger.error("error in repeatedVisitWebPage reason: %s"%str(e))
	browser.quit()

def createObjectDependecyExtractionTraces(url,hostList,configureFilePath,logFileBaseName=None,threshold=10):
	logger.debug("Start create ObjectDependecy traces for website:%s with %d items" % (url,len(hostList)) )
	data = readConfigure(configureFilePath)
	if data == None:
		logger.error("failed to read configure file")
		return

	profile = webdriver.FirefoxProfile(data['firefoxProfilePath'])
	browser = webdriver.Firefox(profile)
	if browser == None:
		logger.error("failed to create firefox instance")
		return 
	o = urlparse(url)
	host = o.netloc;
	if logFileBaseName == None:
		logFileBaseName = 'ODT_'+host+'_%d'
	else:
		logFileBaseName += '_%d'
	count = 0
	for item in hostList:
		count += 1
		try:
			logName = logFileBaseName%count
			repeatedTimes = 0
			logger.debug("Start browsing %s with %s as suspended URL and store the requests at %s"%(url,item,logName) )
			while True:
				p, outFile, errFile = runMitmproxy(data['mitmproxyScriptPath'], \
										url, item, data['logDir'], logName, threshold)
				logger.debug("  done starting mitmproxy");
				openNewTab(browser)
				browser.get(url)
				closeCurrentTab(browser)
				logger.debug("  done browsing %s with %s as suspended URL and store the requests at %s"%(url,item,logName) )
				sendExitSignalToProxy()
				terminateMitmproxy(p, outFile, errFile)
				logger.debug("  done terminating mitmproxy")
				time.sleep(2);
				path = os.path.join(data['logDir'],logName)
				fileSize = os.stat(path).st_size
				if fileSize > 1000:
					logger.debug("  successfully collects %d bytes requests" % fileSize)
					break
				elif repeatedTimes > 5:
					logger.error("  failed to capture requests while browsing %s with %s as suspended URL" % (url,item) )
					break
				else:
					logger.warning("  repeat browsing %s with %s as suspended URL: too few requests captured (%d bytes)" \
									% (url,item,fileSize))
					repeatedTimes += 1
			logger.debug('\n')
		except Exception as e:
			logger.error("error in createObjectDependecyExtractionTraces[%s] reason: %s"%(item,str(e)) )
	browser.quit()

def readHostList(filePath):
	f = open(filePath)
	data = []
	for line in f:
		line = line.strip()
		data.append(line)
	return data

def main():
	hdlr = logging.FileHandler('driver.log')
	formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
	hdlr.setFormatter(formatter)
	#logger.addHandler(hdlr) 
	consoleHandler = logging.StreamHandler()
	consoleHandler.setFormatter(formatter)
	logger.addHandler(consoleHandler)
	logger.setLevel(logging.DEBUG)
	#repeatedVisitWebPage(url,suspendURL,times,configureFilePath,logFileBaseName=None):
	#						url 		times
	#repeatedVisitWebPage(sys.argv[1],10,sys.argv[2])
	#argv1: firstURL
	#argv2: path for hostList
	#argv3: path for configuration 
	hostList = readHostList(sys.argv[2])
	createObjectDependecyExtractionTraces(sys.argv[1],hostList,sys.argv[3],logFileBaseName="DDD")


if __name__ == "__main__":
	main()
	