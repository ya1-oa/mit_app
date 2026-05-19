from django.test.runner import DiscoverRunner

class CustomTestRunner(DiscoverRunner):
    """Custom test runner with additional setup"""
    
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        # Additional test environment setup
    
    def teardown_test_environment(self, **kwargs):
        super().teardown_test_environment(**kwargs)
        # Clean up test environment