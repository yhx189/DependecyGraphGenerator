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
import argparse

####Configure Info######

logger = logging.getLogger('firefox-driver')

#########################################
#			Selenium Utilities			#
#########################################
def openNewTab(browser):
	if sys.platform == "darwin":
		ActionChains(browser).send_keys(Keys.COMMAND, "t").perform()
		ActionChains(browser).send_keys(Keys.COMMAND, "t").perform()
	elif sys.platform == "linux2":
		ActionChains(browser).send_keys(Keys.CONTROL, "t").perform()
		ActionChains(browser).send_keys(Keys.CONTROL, "t").perform()
	else:
		logger.error("openNewTab unsupported OS: %s"%sys.platform)

def closeCurrentTab(browser):
	if sys.platform == "darwin":
		browser.find_element_by_tag_name('body').send_keys(Keys.COMMAND + 'w')
	elif sys.platform == "linux2":
		browser.find_element_by_tag_name('body').send_keys(Keys.CONTROL + 'w')
	else:
		logger.error("closeCurrentTab unsupported OS: %s"%sys.platform)

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
	outFile = open(outFileName,'w+')
	errFileName = os.path.join(logDir,'stderr.txt')
	errFile = open(errFileName,'w+')
	logger.debug("prepare to run mitmproxy %s"%(' '.join(args),))
	p = runBackgroundProcess(args, outFile, errFile)
	errFile.write("write sth for test....\n");
	time.sleep(3)
	p.poll()
	if p.returncode == None:
		logger.debug("successfully run mitmproxy with pid %d "%p.pid)
		return p, outFile, errFile
	else:
		logger.error("failed to run mitmproxy %d"%p.returncode)
		return None, None, None

def terminateMitmproxy(proxyProcess, outFile, errFile):
	try:
		if outFile and not outFile.closed:
			outFile.close()
		if errFile and not errFile.closed:
			errFile.close()
		if proxyProcess != None:
			killProcessAndChildren(proxyProcess.pid)
			time.sleep(2)
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

def repeatedVisitWebPage(url,times,configureFilePath,logFileBaseName=None,useProxy=True):
	logger.debug("Start visiting web page %s for %d times..."%(url,times))
	data = readConfigure(configureFilePath)
	if data == None:
		logger.error("failed to read configure file")
		return
	
	if useProxy:
		profile = webdriver.FirefoxProfile(data['firefoxProfilePathWithProxy'])
	else:
		profile = webdriver.FirefoxProfile(data['firefoxProfilePathWithoutProxy'])
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
	browser.set_page_load_timeout(60)
	#openNewTab(browser)
	for i in range(times):
		try:
			logName = logFileBaseName % i
			if useProxy:
				logger.debug("  start running mitmproxy");
				p, outFile, errFile = runMitmproxy(data['mitmproxyScriptPath'], \
									url, "none", data['logDir'], logName, 10)
				logger.debug("  start browsing %d time and store to file %s"%(i,logName) )
			time.sleep(2)
			openNewTab(browser)
			
			browser.get(url)
			closeCurrentTab(browser)
			logger.debug("  done browsing %d time and store to file %s"%(i,logName) )
			if useProxy:
				sendExitSignalToProxy()
				terminateMitmproxy(p, outFile, errFile)
				logger.debug("  done terminating mitmproxy")
			time.sleep(2);
		except Exception as e:
			logger.error("error [%s] in repeatedVisitWebPage reason: %s. start cleaning states..."%(logName,str(e)) )
			closeCurrentTab(browser)
			logger.debug("  [IN EXCEPTION HANDLER] done closing current tab")
			if useProxy:
				sendExitSignalToProxy()
				terminateMitmproxy(p, outFile, errFile)
				logger.debug("  [IN EXCEPTION HANDLER] done terminating mitmproxy")
			time.sleep(2);
			
			
	browser.quit()

def createObjectDependecyExtractionTraces(url,hostList,configureFilePath,logFileBaseName=None,threshold=10):
	logger.debug("Start create ObjectDependecy traces for website:%s with %d items" % (url,len(hostList)) )
	data = readConfigure(configureFilePath)
	if data == None:
		logger.error("failed to read configure file")
		return

	profile = webdriver.FirefoxProfile(data['firefoxProfilePathWithProxy'])
	browser = webdriver.Firefox(profile)
	if browser == None:
		logger.error("failed to create firefox instance")
		return 
	browser.set_page_load_timeout(180)
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
			p = None
			outFile = None
			errFile = None
			errCount = 0
			while True:
				p, outFile, errFile = runMitmproxy(data['mitmproxyScriptPath'], \
										url, item, data['logDir'], logName, threshold)
				if p == None:
					errCount += 1
					logger.error("failed to run mitmproxy, do it again... [%d] "%errCount)
					continue
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
			closeCurrentTab(browser)
			sendExitSignalToProxy()
			terminateMitmproxy(p, outFile, errFile)
			logger.debug("  done terminating mitmproxy")
			time.sleep(2);
	browser.quit()

def readHostList(filePath):
	f = open(filePath)
	data = []
	for line in f:
		line = line.strip()
		data.append(line)
	return data

def parse_arguments():
	parser = argparse.ArgumentParser()
	parser.add_argument('--function','-f', help='the function to execute')
	parser.add_argument('--prefix','-p', help='prefix of file names')
	parser.add_argument('--configurepath','-c', help='the path of configure file')
	parser.add_argument('--dir','-d', help='directory of log files')
	parser.add_argument('--times','-t',type=int, help='the times of browsing a file')
	parser.add_argument('--timeout','-to',type=int, help='the timeout of loading a page')
	parser.add_argument('--firsturl','-fu', help='the first url of each trace')
	#parser.add_argument('--os','-os', help='the operating system type')
	#parser.add_argument('--lasturl','-lu', help='the last url of each trace')
	parser.add_argument('--commonhostlist','-ch', help='the path of valid object url list')
	args = parser.parse_args()
	try:
		o = urlparse(args.firsturl)
	except Exception as e:
		parser.print_help()
		return None
	return args

def main():
	hdlr = logging.FileHandler('driver.log')
	formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
	hdlr.setFormatter(formatter)
	logger.addHandler(hdlr) 
	consoleHandler = logging.StreamHandler()
	consoleHandler.setFormatter(formatter)
	logger.addHandler(consoleHandler)
	logger.setLevel(logging.DEBUG)
	
	args = parse_arguments()
	if not args:
		return
	if args.function == "normalvisit":
		logger.debug("repated visit %s for %d times without proxy" % (args.firsturl,args.times))
		repeatedVisitWebPage(args.firsturl,args.times,args.configurepath,args.prefix,useProxy=False)
	elif args.function == "proxyvisit":
		logger.debug("repated visit %s for %d times with proxy" % (args.firsturl,args.times))
		repeatedVisitWebPage(args.firsturl,args.times,args.configurepath,args.prefix,useProxy=True)
	elif args.function == "createdependencygraph":
		logger.debug("create dependency graph for %s with timeout %d" %(args.firsturl,args.timeout))
		#argv1: firstURL
		#argv2: path for hostList
		#argv3: path for configuration 
		hostList = readHostList(args.commonurllist)
		createObjectDependecyExtractionTraces(args.firsturl,args.commonurllist,args.configurepath,args.prefix,args.timeout)
	#repeatedVisitWebPage(url,times,configureFilePath,logFileBaseName=None,useProxy=False):
	#						url 		times
	#repeatedVisitWebPage(sys.argv[1],10,sys.argv[2],useProxy=True,logFileBaseName="TSINA2")

	#createObjectDependecyExtractionTraces(url,hostList,configureFilePath,logFileBaseName=None,threshold=10)
	#argv1: firstURL
	#argv2: path for hostList
	#argv3: path for configuration 
	#hostList = readHostList(sys.argv[2])
	#createObjectDependecyExtractionTraces(sys.argv[1],hostList,sys.argv[3],logFileBaseName="sinagraph",threshold=30)


if __name__ == "__main__":
	main()
	