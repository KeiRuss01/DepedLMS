from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class ExistingAccountOnlyAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, socialaccount):
        # Google can only log in accounts already registered in the LMS.
        return False