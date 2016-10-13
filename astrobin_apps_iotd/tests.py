# Django
from datetime import datetime, timedelta

# Django
from django.conf import settings
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse_lazy
from django.test import TestCase

# Third party
from bs4 import BeautifulSoup as BS
from beautifulsoupselect import BeautifulSoupSelect as BSS
import simplejson as json

# AstroBin
from astrobin.models import Image

# This app
from astrobin_apps_iotd.models import *


class IotdTest(TestCase):
    def setUp(self):
        self.submitter_1 = User.objects.create_user('submitter_1', 'submitter_1@test.com', 'password')
        self.submitter_2 = User.objects.create_user('submitter_2', 'submitter_2@test.com', 'password')
        self.submitters = Group.objects.create(name = 'iotd_submitters')
        self.submitters.user_set.add(self.submitter_1, self.submitter_2)

        self.reviewer_1 = User.objects.create_user('reviewer_1', 'reviewer_1@test.com', 'password')
        self.reviewer_2 = User.objects.create_user('reviewer_2', 'reviewer_2@test.com', 'password')
        self.reviewers = Group.objects.create(name = 'iotd_reviewers')
        self.reviewers.user_set.add(self.reviewer_1, self.reviewer_2)

        self.user = User.objects.create_user('user', 'user@test.com', 'password')
        self.client.login(username = 'user', password = 'password')
        self.client.post(
            reverse_lazy('image_upload_process'),
            { 'image_file': open('astrobin/fixtures/test.jpg', 'rb') },
            follow = True)
        self.client.logout()
        self.image = Image.objects.all()[0]


    def tearDown(self):
        self.submitters.delete()
        self.submitter_1.delete()
        self.submitter_2.delete()

        self.reviewers.delete()
        self.reviewer_1.delete()
        self.reviewer_2.delete()

        self.user.delete()
        self.image.delete()

    def test_submission_model(self):
        # User must be submitter
        with self.assertRaisesRegexp(ValidationError, "not a member"):
            IotdSubmission.objects.create(
                submitter = self.user,
                image = self.image)

        # Image must be recent enough
        self.image.uploaded =\
            datetime.now() -\
            timedelta(
                weeks = settings.IOTD_SUBMISSION_WINDOW_WEEKS,
                days = 1)
        self.image.save()
        with self.assertRaisesRegexp(ValidationError, "uploaded more than"):
            IotdSubmission.objects.create(
                submitter = self.submitter_1,
                image = self.image)

        # Image must not be WIP
        self.image.uploaded = datetime.now()
        self.image.is_wip = True
        self.image.save()
        with self.assertRaisesRegexp(ValidationError, "staging area"):
            IotdSubmission.objects.create(
                submitter = self.submitter_1,
                image = self.image)
        self.image.is_wip = False
        self.image.save()

        # Cannot submit own image
        self.image.user = self.submitter_1
        self.image.save()
        with self.assertRaisesRegexp(ValidationError, "your own image"):
            IotdSubmission.objects.create(
                submitter = self.submitter_1,
                image = self.image)
        self.image.user = self.user
        self.image.save()

        # All OK
        submission = IotdSubmission.objects.create(
            submitter = self.submitter_1,
            image = self.image)
        self.assertEqual(submission.submitter, self.submitter_1)
        self.assertEqual(submission.image, self.image)

        # Image cannot be submitted again
        with self.assertRaisesRegexp(ValidationError, "already exists"):
            IotdSubmission.objects.create(
                submitter = self.submitter_1,
                image = self.image)

        # Test max daily
        with self.assertRaisesRegexp(ValidationError, "already submitted.*today"):
            image2 = Image.objects.create(user = self.user)
            with self.settings(IOTD_SUBMISSION_MAX_PER_DAY = 1):
                IotdSubmission.objects.create(
                    submitter = self.submitter_1,
                    image = image2)

    def test_vote_model(self):
        # User must be reviewer
        with self.assertRaisesRegexp(ValidationError, "not a member"):
            IotdVote.objects.create(
                reviewer = self.user,
                image = self.image)

        # Image must have been submitted
        with self.assertRaisesRegexp(ValidationError, "not been submitted"):
            IotdVote.objects.create(
                reviewer = self.reviewer_1,
                image = self.image)
        submission_1 = IotdSubmission.objects.create(
            submitter = self.submitter_1,
            image = self.image)

        # Submission must be within window
        IotdSubmission.objects.filter(pk = submission_1.pk).update(
            date = \
                datetime.now() -\
                timedelta(
                    weeks = settings.IOTD_REVIEW_WINDOW_WEEKS,
                    days = 1))
        with self.assertRaisesRegexp(ValidationError, "in the review queue for more than"):
            IotdVote.objects.create(
                reviewer = self.reviewer_1,
                image = submission_1.image)
        IotdSubmission.objects.filter(pk = submission_1.pk).update(
            date = datetime.now())

        # Image must not be WIP
        self.image.is_wip = True
        self.image.save()
        with self.assertRaisesRegexp(ValidationError, "staging area"):
            IotdVote.objects.create(
                reviewer = self.reviewer_1,
                image = submission_1.image)
        self.image.is_wip = False
        self.image.save()

        # Cannot vote for own image
        self.image.user = self.reviewer_1
        self.image.save()
        with self.assertRaisesRegexp(ValidationError, "your own image"):
            IotdVote.objects.create(
                reviewer = self.reviewer_1,
                image = submission_1.image)
        self.image.user = self.user
        self.image.save()

        # Cannot vote for own submission
        self.submitters.user_set.add(self.reviewer_1)
        submission_1.submitter = self.reviewer_1
        submission_1.save()
        with self.assertRaisesRegexp(ValidationError, "your own submission"):
            IotdVote.objects.create(
                reviewer = self.reviewer_1,
                image = submission_1.image)
        self.submitters.user_set.remove(self.reviewer_1)
        submission_1.submitter = self.submitter_1
        submission_1.save()

        # All OK
        vote = IotdVote.objects.create(
            reviewer = self.reviewer_1,
            image = submission_1.image)
        self.assertEqual(vote.reviewer, self.reviewer_1)
        self.assertEqual(vote.image, submission_1.image)

        # Cannot vote again for the same
        with self.assertRaisesRegexp(ValidationError, "already exists"):
            IotdVote.objects.create(
                reviewer = self.reviewer_1,
                image = submission_1.image)

        # Test max daily
        image2 = Image.objects.create(user = self.user)
        submission_2 = IotdSubmission.objects.create(
            submitter = self.submitter_2,
            image = image2)
        with self.assertRaisesRegexp(ValidationError, "already voted.*today"):
            with self.settings(IOTD_REVIEW_MAX_PER_DAY = 1):
                IotdVote.objects.create(
                    reviewer = self.reviewer_1,
                    image = submission_2.image)

        submission_1.delete()
        submission_2.delete()
        image2.delete()

    def test_submission_create_view(self):
        url = reverse_lazy('iotd_submission_create')

        # Login required
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        # Only submitters allowed
        self.client.login(username = 'user', password = 'password')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        # GET not allowed
        self.client.login(username = 'submitter_1', password = 'password')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

        # Success
        response = self.client.post(url, {
            'submitter': self.submitter_1.pk,
            'image': self.image.pk,
        })
        self.assertEqual(IotdSubmission.objects.count(), 1)

    def test_submission_queue_view(self):
        url = reverse_lazy('iotd_submission_queue')

        # Login required
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

        # Only reviewers allowed
        self.client.login(username = 'submitter_1', password = 'password')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

        self.client.login(username = 'reviewer_1', password = 'password')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Check that images are rendered
        submission_1 = IotdSubmission.objects.create(submitter = self.submitter_1, image = self.image)
        response = self.client.get(url)
        self.assertContains(response, 'data-id="%s"' % self.image.pk)

        # Check that multiple submissions for the same image result in one single image rendered
        submission_2 = IotdSubmission.objects.create(submitter = self.submitter_2, image = self.image)
        response = self.client.get(url)
        bss = BSS(response.content)
        self.assertEqual(len(bss('.astrobin-image-container')), 1)

        # Check for count badge
        self.assertEqual(bss('.iotd-queue-item .badge')[0].text, '2')
        submission_2.delete()

        # Check for may-not-vote class
        submission_1.submitter = self.reviewer_1
        self.submitters.user_set.add(self.reviewer_1)
        submission_1.save()
        response = self.client.get(url)
        bs = BS(response.content)
        self.assertEqual(len(bs.select('.iotd-queue-item.may-not-vote')), 1)
        self.submitters.user_set.remove(self.reviewer_1)
        submission_1.submitter = self.submitter_1
        submission_1.save()

    def test_toggle_vote_ajax_view(self):
        url = reverse_lazy('iotd_toggle_vote_ajax', kwargs = {'pk': self.image.pk});

        # Login required
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

        # Only reviewers allowed
        self.client.login(username = 'submitter_1', password = 'password')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

        # GET not allowed
        self.client.login(username = 'reviewer_1', password = 'password')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

        # Only AJAX allowed
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

        # All OK
        submission = IotdSubmission.objects.create(
            submitter = self.submitter_1,
            image = self.image)
        response = self.client.post(url, HTTP_X_REQUESTED_WITH = 'XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['vote'], 1)
        self.assertEqual(json.loads(response.content)['toggled'], True)
        self.assertEqual(json.loads(response.content)['error'], None)
        self.assertEqual(IotdVote.objects.count(), 1)

        # Toggle off
        response = self.client.post(url, HTTP_X_REQUESTED_WITH = 'XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['vote'], None)
        self.assertEqual(json.loads(response.content)['toggled'], False)
        self.assertEqual(json.loads(response.content)['error'], None)
        self.assertEqual(IotdVote.objects.count(), 0)