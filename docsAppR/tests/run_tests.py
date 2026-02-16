#!/usr/bin/env python
import os
import sys
import django
from django.test.utils import get_runner
from django.conf import settings

if __name__ == "__main__":
    os.environ['DJANGO_SETTINGS_MODULE'] = 'mitigation_app.settings'
    django.setup()
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, failfast=False)
    
    # Run all tests
    failures = test_runner.run_tests(['docsAppR.tests'])
    
    sys.exit(bool(failures))