
# Media Storage to be served locally
from django.conf import settings
from django.conf.urls.static import static
# others
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from custom.views import home, about, contact, clients, dcc, how_to_videos, features, rates, brochure
from moromafinance.media_views import protected_media

urlpatterns = [

    # Authenticated serving of uploaded KYC documents / payslips / IDs.
    path('media/<path:path>', protected_media, name='protected_media'),

    path('appadmin/', admin.site.urls),
    path('ckeditor/', include('ckeditor_uploader.urls')),
    path('accounts/', include('accounts.urls')),
    path('admin/', include('admin1.urls')),
    path('staff/', include('staff.urls')),
    path('loan/', include('loan.urls')),
    path('message/', include('message.urls')),
    path('support/', include('support.urls')),
    path('custom/', include('custom.urls')),
    path('API/', include('api.urls')),
    path('report/', include('report.urls')),
    path('dcc/', include('dcc.urls')),
    path('admin/referrers/', include('referral.urls')),
    path('manager/', include('manager.urls')),

    #website url paths
    re_path(r'^$', home, name='home'),
    path('about/', about, name='about'),
    path('contact/', contact, name='contact'),
    path('clients/', clients, name='clients'),
    path('dcc/', dcc, name='dcc'),
    path('how-to-videos/', how_to_videos, name='how_to_videos'),
    path('features/', features, name='features'),
    path('rates/', rates, name='rates'),
    # Old path kept so any existing link/bookmark still lands on the page.
    path('pricing/', RedirectView.as_view(pattern_name='rates', permanent=True)),
    path('brochure/', brochure, name='brochure'),

    
    
    
    #Django Jet Admin
    #path('jet/', include('jet.urls', 'jet')),
    #path('jet/dashboard/', include('jet.dashboard.urls', 'jet-dashboard')),
]

# Media Storage to be served locally
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    import debug_toolbar
    urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
    
    



