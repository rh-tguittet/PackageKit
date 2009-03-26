import os
from xml.dom.minidom import parse, parseString
from xml.parsers.expat import ExpatError
import urllib as url


from conary.lib import sha1helper
from conary.lib import util

from packagekit.backend import PackageKitBaseBackend
from packagekit.enums import ERROR_NO_CACHE,ERROR_REPO_CONFIGURATION_ERROR


from pkConaryLog import log
from conarypk import ConaryPk
from conaryEnums import groupMap

def getGroup( categorieList ):
    where = mapGroup( categorieList )
    if where.values():
        return max( where.iteritems())[0]
    else:
        return None



def mapGroup(categorieList):
    where = {}
    if  not categorieList:
        return where
    #log.info(categorieList)
    for cat in categorieList:
        for group,categories in groupMap.items():
            if cat in categories:
                if group in where:
                    where[group] = where[group] +1
                else:
                    where[group] = 1
    return where

class XMLRepo:
    xml_path = ""
    repository = ""
    def __init__(self, repo, path ):
        self.xml_path = path
        self._setRepo(repo)

    def resolve(self, search_trove):
        """ resolve its a search with name """
        trove =  self._getPackage(search_trove)
        if trove:
            return trove
        else:
            return None
        
    def search(self, search, where ):
        if where == "name":
            r = self._searchNamePackage(search)
        elif where == "details":
            r = self._searchDetailsPackage(search)
        elif where == "group":
            r = self._searchGroupPackage(search)
        else:
            r = self._searchPackage(search)

        names = set( [i["name"] for i in r] )
        results = []
        for i in r:
            if i["name"] in names:
                results.append(i)
                names.remove(i["name"])
        return results
            

    def _setRepo(self,repo):  
        self.repo = repo
        doc = self._open()
        self.label = str( doc.childNodes[0].getAttribute("label") )

    def _open(self):
        try:
            return self._repo
        except AttributeError:
            try:
                self._repo =   parse(open( self.xml_path + self.repo))
                return self._repo
            except ExpatError:
                Pk = PackageKitBaseBackend("")
                Pk.error(ERROR_REPO_CONFIGURATION_ERROR," The file %s not parsed submit a issue " % ( self.xml_path + self.repo, ) )
       

    def _generatePackage(self, package_node ): 
        """ convert from package_node to dictionary """
        pkg = {}
        cat = []
        for node in package_node.childNodes:
            if pkg.has_key('category'):
                cat.append(str(node.childNodes[0].nodeValue).replace(";","").replace("#",""))
            else:
                pkg[node.nodeName.encode("UTF-8")] = str(node.childNodes[0].nodeValue.encode("UTF-8")).replace(";",' ').replace("#","")
        pkg["category"] = cat
        return pkg

    def _getPackage(self, name):
        doc = self._open()
        results = []
        for packages in doc.childNodes:
            for package in packages.childNodes:
                pkg = self._generatePackage(package)
                pkg["label"] = self.label
                if name == pkg["name"]:
                    return pkg
        return None

    def _searchNamePackage(self, name):
        doc = self._open()
        results = []
        for packages in doc.childNodes:
            for package in packages.childNodes:
                pkg = self._generatePackage(package)
                pkg["label"] = self.label
                if name.lower() in pkg["name"].lower():
                    results.append(pkg)
        return  results

    def _searchGroupPackage(self, name):
        doc = self._open()
        results_name = []
        for packages in doc.childNodes:
            for package in packages.childNodes:
                pkg = self._generatePackage(package)
                pkg["label"] = self.label
                if pkg.has_key("category"):
                    group = getGroup(pkg["category"])
                    if name.lower() == group:
                        results_name.append(pkg)
            #log.info(results_name)
        return results_name

    def _searchDetailsPackage(self, name):
        return self._searchPackage(name)
    def _searchPackage(self, name):
        doc = self._open()
        results = []
        for packages in doc.childNodes:
            for package in packages.childNodes:
                pkg = self._generatePackage(package)
                pkg["label"] = self.label
                for i in pkg.keys():
                    if i  == "label":
                        continue
                    if i =='category':
                        for j in pkg[i]:
                            if name.lower() in j.lower():
                                results.append(pkg)
                    
                    if type(pkg[i]) == str:
                        check = pkg[i].lower()
                    else:
                        check = pkg[i]
                    if name.lower() in check:
                        results.append(pkg)
            
        return results
    def _getAllPackages(self):
        doc = self._open()
        results = []
        for packages in doc.childNodes:
            for package in packages.childNodes:
                pkg = self._generatePackage(package)
                pkg["label"] = self.label
                results.append(pkg)
        return results


class XMLCache:
    #xml_files = ["foresight.rpath.org@fl:2"]
    xml_files = []
    server = "http://packages.foresightlinux.org/cache/"
    repos = []
    dbPath = '/var/cache/conary/'
    jobPath = dbPath + 'jobs'
    xml_path =  dbPath + "xmlrepo/"

    def __init__(self):
        con = ConaryPk()
        labels = con.get_labels_from_config()

        if not os.path.isdir(self.dbPath):
            os.makedirs(self.dbPath)
        if not os.path.isdir(self.jobPath):
            os.mkdir(self.jobPath)
        if not os.path.isdir( self.xml_path ):
            os.makedirs(self.xml_path )
 
        for xml_file in labels:
           if not os.path.exists( self.xml_path + xml_file + ".xml"  ):
                self._fetchXML()
        for xml_file in labels :
            self.repos.append(XMLRepo( xml_file + ".xml", self.xml_path ))

    def _getJobCachePath(self, applyList):
        applyStr = '\0'.join(['%s=%s[%s]--%s[%s]%s' % (x[0], x[1][0], x[1][1], x[2][0], x[2][1], x[3]) for x in applyList])
        return self.jobPath + '/' + sha1helper.sha1ToString(sha1helper.sha1String(applyStr))

    def checkCachedUpdateJob(self, applyList):
        jobPath = self._getJobCachePath(applyList)
        log.info("CheckjobPath %s" % jobPath)
        if os.path.exists(jobPath):
            return jobPath
    
    def cacheUpdateJob(self, applyList, updJob):
        jobPath = self._getJobCachePath(applyList)
        log.info("jobPath %s" % jobPath)
        if os.path.exists(jobPath):
            log.info("deleting the JobPath %s "% jobPath)
            util.rmtree(jobPath)
            log.info("end deleting the JobPath %s "% jobPath)
        log.info("making the logPath ")
        os.mkdir(jobPath)
        log.info("freeze JobPath")
        updJob.freeze(jobPath)

    def convertTroveToDict(self, troveTupleList):
        mList = []
        for troveTuple in troveTupleList: 
            pkg = {}
            pkg["name"] = troveTuple[0]
            pkg["version"] = troveTuple[1].trailingRevision()
            pkg["label"] = troveTuple[1].trailingLabel() 
            mList.append(pkg)
        return mList
            
    def searchByGroups(self, groups):
        pass
    def refresh(self):
        self._fetchXML()
    def resolve(self, name ):
        for repo in self.repos:
            r =  repo.resolve(name)
            if r:
                return r
        else:
            return None

    def search(self, search, where = "name" ):
        """ 
            @where (string) values = name | details | group |
        """
        repositories_result = []
        for repo in self.repos:
            results = repo.search(search , where )
            for i in results:
                repositories_result.append(i)
        return repositories_result

    def _fetchXML(self ):
        con = ConaryPk()
        labels = con.get_labels_from_config()
        for i in labels:
            label = i + '.xml'
            filename = self.xml_path + label
            wwwfile = self.server + label
            try:
                wget = url.urlopen( wwwfile )
            except:
                Pk = PackageKitBaseBackend("")
                Pk.error(ERROR_NO_CACHE," %s can not open" % wwwfile)
            openfile = open( filename ,'w')
            openfile.writelines(wget.readlines())
            openfile.close()
    def getGroup(self,categorieList):
        return getGroup(categorieList)
                
    def _getCategorieBase(self, mapDict, categorieList ):
        if not categorieList:
            return None

        tempDict = {}
        for cat in categorieList:

            if mapDict.has_key(cat):
                map = mapDict[cat]
            else:
                continue

            if tempDict.has_key(map):
                tempDict[map] = tempDict[map] + 1
            else:
                tempDict[map] = 1
        tmp = 0
        t_key = ""
        for key, value in tempDict.items():
            if value > tmp:
                t_key =  key
                tmp  = value
        return t_key

    def _getAllCategories(self):
        categories = []
        for i in self.repos:
            pkgs = i._getAllPackages()
            for pkg in pkgs:
                if pkg.has_key('category'):
                    for cat in pkg["category"]:
                        categories.append(cat)
        categories.sort()
        return set( categories )
        
        

if __name__ == '__main__':
  #  print ">>> name"
    import sys
    l= XMLCache().search(sys.argv[1],sys.argv[2] )
   # print ">> details"
   # l= XMLCache().search('Internet', 'group' )

    for v,p in enumerate(l):
        print v,p["name"]
    #print  XMLCache().getGroup(['GTK', 'Graphics', 'Photography', 'Viewer'])
