__author__="Stefano Mosconi <stefano.mosconi@gmail.com>"
__date__ ="$Sep 7, 2011 10:32:47 PM$"

from setuptools import setup,find_packages

def debpkgver(changelog = "debian/changelog"):
    return open(changelog).readline().split(' ')[1][1:-1]

setup (
  name = 'python-vcs-commit',
  version = debpkgver(),
  packages = find_packages(),

  # Fill in these to make your Egg ready for upload to
  # PyPI
  author = 'Stefano Mosconi',
  author_email = 'stefano.mosconi@gmail.com',

  description = 'Simple script that comments on bugzilla',
  license = 'GPL',
  long_description= '''
  Parses the changelog contained in a commit message (either SVN or GIT) 
  and then comments on bugzilla the relevant bug
  ''',
  py_modules=["vcscommit"],

  # could also include long_description, download_url, classifiers, etc.

  classifiers=[
      "Development Status :: 4 - Beta",
      "Operating System :: Unix",
      "License :: OSI Approved :: GNU General Public License (GPL)",
      "Intended Audience :: System Administrators",
      "Programming Language :: Python",
      "Topic :: Tools :: Bugzilla"
  ]
  
)
