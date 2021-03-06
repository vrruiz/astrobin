# Django
from django.conf.urls import patterns, url, include
from django.contrib.auth.decorators import login_required
from django.views.generic import *

# This app
from astrobin_apps_donations.views import *

urlpatterns = patterns('',
    url(
        r'^cancel/$',
        CancelView.as_view(),
        name = 'astrobin_apps_donations.cancel'),

    url(
        r'^success/$',
        SuccessView.as_view(),
        name = 'astrobin_apps_donations.success'),

    url(
        r'^edit/',
        login_required(EditView.as_view()),
        name = 'astrobin_apps_donations.edit'),

    url(r'^paypal/', include('paypal.standard.ipn.urls')),
)

