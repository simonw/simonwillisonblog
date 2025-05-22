import os
import boto3
from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.conf import settings
from django.conf import settings
from django import forms
from datetime import datetime
from botocore.exceptions import ClientError, NoCredentialsError

MAX_UPLOAD_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")


@require_http_methods(["GET", "POST"])
def image_upload_view(request):
    """Function-based view for handling image uploads"""

    if request.method == "GET":
        form = ImageUploadForm()
        return render(request, "image_upload.html", {"form": form})

    elif request.method == "POST":
        # Check if it's an AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            try:
                if "image" not in request.FILES:
                    return JsonResponse(
                        {"success": False, "error": "No image file provided"},
                        status=400,
                    )

                image = request.FILES["image"]
                form = ImageUploadForm(request.POST, request.FILES)

                if form.is_valid():
                    uploader = S3ImageUploader()
                    image.seek(0)  # Reset file pointer
                    result = uploader.upload_image(image, image.name)

                    if result["success"]:
                        return JsonResponse(result)
                    else:
                        return JsonResponse(result, status=500)
                else:
                    return JsonResponse(
                        {"success": False, "error": list(form.errors.values())[0][0]},
                        status=400,
                    )

            except Exception as e:
                return JsonResponse(
                    {"success": False, "error": "Upload failed due to server error"},
                    status=500,
                )

        # Handle regular form submission
        else:
            form = ImageUploadForm(request.POST, request.FILES)

            if form.is_valid():
                image = form.cleaned_data["image"]
                uploader = S3ImageUploader()
                image.seek(0)
                result = uploader.upload_image(image, image.name)

                if result["success"]:
                    return render(
                        request,
                        "image_upload_success.html",
                        {"url": result["url"], "key": result["key"]},
                    )
                else:
                    form.add_error("image", result["error"])

            return render(request, "image_upload.html", {"form": form})


class ImageUploadForm(forms.Form):
    image = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
        help_text="Upload an image file (JPG, PNG, GIF, WebP). Max size: 5MB",
    )

    def clean_image(self):
        image = self.cleaned_data.get("image")

        if not image:
            raise ValidationError("No image file provided.")

        # Check file size
        if image.size > MAX_UPLOAD_SIZE:
            raise ValidationError(
                f"File size must be less than {MAX_UPLOAD_SIZE / (1024*1024):.1f}MB"
            )

        # Check file extension
        ext = os.path.splitext(image.name)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValidationError(
                f"Unsupported file format. Allowed formats: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
            )

        return image


class S3ImageUploader:
    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME

    def generate_s3_key(self, filename):
        """Generate S3 key with format: static/YYYY/filename.ext"""
        current_year = datetime.now().year
        base_name, ext = os.path.splitext(filename)
        # Sanitize filename (remove special characters, spaces)
        safe_base_name = "".join(
            c for c in base_name if c.isalnum() or c in ("-", "_")
        ).strip()
        if not safe_base_name:
            safe_base_name = "image"

        return f"static/{current_year}/{safe_base_name}{ext.lower()}"

    def check_key_exists(self, key):
        """Check if a key already exists in S3"""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            else:
                raise e

    def get_unique_key(self, base_key):
        """Generate a unique key by appending numbers if necessary"""
        if not self.check_key_exists(base_key):
            return base_key

        # Extract parts of the key
        path_parts = base_key.split("/")
        filename_with_ext = path_parts[-1]
        path_prefix = "/".join(path_parts[:-1])

        base_name, ext = os.path.splitext(filename_with_ext)

        counter = 2
        while counter <= 1000:  # Prevent infinite loop
            new_filename = f"{base_name}-{counter}{ext}"
            new_key = f"{path_prefix}/{new_filename}"

            if not self.check_key_exists(new_key):
                return new_key

            counter += 1

        # If we've tried 1000 variations, use timestamp
        timestamp = int(datetime.now().timestamp())
        fallback_filename = f"{base_name}-{timestamp}{ext}"
        return f"{path_prefix}/{fallback_filename}"

    def upload_image(self, file_obj, original_filename):
        """Upload image to S3 and return the final key and URL"""
        try:
            # Generate base S3 key
            base_key = self.generate_s3_key(original_filename)

            # Get unique key (handle duplicates)
            final_key = self.get_unique_key(base_key)

            # Upload file
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                final_key,
                ExtraArgs={
                    "ContentType": self._get_content_type(original_filename),
                    "ACL": "public-read",  # Make publicly readable
                },
            )

            # Generate public URL
            url = f"https://static.simonwillison.net/{final_key}"

            return {
                "success": True,
                "key": final_key,
                "url": url,
                "bucket": self.bucket_name,
            }

        except NoCredentialsError:
            return {"success": False, "error": "AWS credentials not configured"}
        except ClientError as e:
            return {"success": False, "error": f"S3 upload failed: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Upload failed: {str(e)}"}

    def _get_content_type(self, filename):
        """Get content type based on file extension"""
        ext = os.path.splitext(filename)[1].lower()
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return content_types.get(ext, "application/octet-stream")
