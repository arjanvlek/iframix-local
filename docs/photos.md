# Photos

There are 2 methods to view photos: "Photos" and "Photos + AI".

## Local replacement for AI mode

In the real product, photos with AI are processed by an AI service, which generates a title and a quote that should match the content of the photo (but works terribly in practice).

In this local implementation, no such AI service is present. Instead, image capture date, camera model and exposure settings are displayed. This is determined from the image's EXIF data.

The webapp picks one of several layout templates per AI photo (5 horizontal styles, 4 vertical styles on a 16:9 iPad; 10 of each on a 4:3 iPad). A random template is selected at upload time (and on first read for photos dropped directly into `photos_with_ai/`)

### Known issue with 16:9 screens

The 16:9 horizontal templates are shipped in the webapp bundle, but do not actually render correctly. This is a known issue that
iFramix should fix in a new app update.

## Local replacement for cloud uploads

In the real product, photos are uploaded to the cloud using either the Qiniu SDK (up to app 2.2.27) or Cloudflare R2 storage (app 2.2.29+).

In this local implementation, photos are served from the `photos` and `photos_with_ai` directories on your own server instead.

Photos are stored per device in `photos/{device_id}/` (normal photo viewer) or `photos_with_ai/{device_id}/` (AI photo viewer). 
Each display device has its own photo collection, identified by `device_id`.

The upload flow is simulated in such a way that upload traffic for the Qiniu SDK is redirected to a POST endpoint on `/`. 
The Cloudflare R2 upload is directly handled by the `/api/user/asset/uploader` endpoint.
This allows you to upload photos form the control app as usual, but these don't end up in any cloud service.

## Photo upload / classification flow

When photos are uploaded from the app, they follow a two-step flow: the upload endpoint saves to a temporary `photos_temp/` directory, 
then a classification request moves each file to the correct device subdirectory based on whether it is a normal or AI photo.
