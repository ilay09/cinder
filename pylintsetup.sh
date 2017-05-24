find /var/lib/jenkins/workspace/$JOB_NAME/keystone/auth -iname "*.py" |xargs pylint --disable=/var/lib/jenkins/workspace/keystone_pylint/keystone/tests/
