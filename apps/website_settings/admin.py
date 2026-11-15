from django.contrib import admin

from .models import FAQ, Banner, BlogPost, HomeSection, InstagramPost, NewsletterSubscriber, StaticPage, Testimonial, WebsiteSetting

for model in (WebsiteSetting, Banner, HomeSection, StaticPage, BlogPost, Testimonial, FAQ, InstagramPost, NewsletterSubscriber):
    admin.site.register(model)
