"""
Reading Browser app views.
"""
import json
import os
import zipfile

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from docsAppR.models import ReadingImage


def reading_browser(request):
    """Main view for the reading browser"""
    images = ReadingImage.objects.all()
    return render(request, 'account/browser.html', {'images': images})


@csrf_exempt
def upload_readings(request):
    """Handle image uploads"""
    if request.method == 'POST' and request.FILES.getlist('images'):
        uploaded_files = request.FILES.getlist('images')
        results = {
            'success': [],
            'errors': [],
            'duplicates': []
        }

        for uploaded_file in uploaded_files:
            # Check if file already exists
            if ReadingImage.objects.filter(filename=uploaded_file.name).exists():
                results['duplicates'].append(uploaded_file.name)
                continue

            try:
                # Create new ReadingImage
                reading_image = ReadingImage(
                    filename=uploaded_file.name,
                    size=uploaded_file.size,
                    file=uploaded_file
                )
                reading_image.save()
                results['success'].append(uploaded_file.name)
            except Exception as e:
                results['errors'].append(f"{uploaded_file.name}: {str(e)}")

        return JsonResponse(results)

    return JsonResponse({'error': 'No files provided'}, status=400)


def get_sorted_readings(request):
    """Get sorted images based on criteria"""
    sort_by = request.GET.get('sort_by', 'filename')  # Default to filename sort
    order = request.GET.get('order', 'asc')

    images = ReadingImage.objects.all()

    # Apply sorting
    if sort_by == 'rh':
        field = 'rh_value'
    elif sort_by == 't':
        field = 't_value'
    elif sort_by == 'gpp':
        field = 'gpp_value'
    elif sort_by == 'mc':
        field = 'mc_value'
    elif sort_by == 'filename':
        field = 'filename'
    else:
        field = 'filename'  # Default to filename sorting

    if order == 'desc':
        field = f'-{field}'

    images = images.order_by(field)

    # Prepare data for JSON response
    image_data = []
    for image in images:
        image_data.append({
            'id': image.id,
            'filename': image.filename,
            'url': image.file.url,
            'rh': image.rh_value,
            't': image.t_value,
            'gpp': image.gpp_value,
            'mc': image.mc_value,
            'size': image.get_file_size_display()
        })

    return JsonResponse({'images': image_data})


@csrf_exempt
def export_readings(request):
    """Export selected images as zip file with better error handling"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            folder_structure = data.get('folders', {})

            if not folder_structure:
                return JsonResponse({'error': 'No folders provided'}, status=400)

            # Validate that we have some images to export
            total_images = sum(len(images) for images in folder_structure.values())
            if total_images == 0:
                return JsonResponse({'error': 'No images in folders to export'}, status=400)

            # Create zip file in memory
            response = HttpResponse(content_type='application/zip')
            response['Content-Disposition'] = 'attachment; filename="reading_images.zip"'

            try:
                with zipfile.ZipFile(response, 'w') as zip_file:
                    exported_count = 0
                    missing_files = []

                    for folder_name, image_data_list in folder_structure.items():
                        for image_data in image_data_list:
                            try:
                                image_id = image_data.get('id')
                                image = ReadingImage.objects.get(id=image_id)

                                if image.file and os.path.exists(image.file.path):
                                    # Add to folder in zip
                                    zip_path = os.path.join(folder_name, image.filename)
                                    zip_file.write(image.file.path, zip_path)
                                    exported_count += 1
                                else:
                                    missing_files.append(image.filename)

                            except ReadingImage.DoesNotExist:
                                missing_files.append(f"Image ID {image_id}")
                            except Exception as e:
                                missing_files.append(f"{image_data.get('filename', 'Unknown')}: {str(e)}")

                    if exported_count == 0:
                        return JsonResponse({
                            'error': f'No files could be exported. Missing files: {missing_files}'
                        }, status=404)

                    if missing_files:
                        print(f"Warning: {len(missing_files)} files could not be exported: {missing_files}")

                return response

            except zipfile.BadZipFile:
                return JsonResponse({'error': 'Error creating zip file'}, status=500)
            except OSError as e:
                return JsonResponse({'error': f'File system error: {str(e)}'}, status=500)

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Unexpected error: {str(e)}'}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=400)


@csrf_exempt
def rename_reading(request, image_id):
    """Rename a reading image and properly update the file field"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_filename = data.get('filename')

            if not new_filename:
                return JsonResponse({'error': 'No filename provided'}, status=400)

            image = ReadingImage.objects.get(id=image_id)

            # Get the current file information
            if not image.file:
                return JsonResponse({'error': 'Image file not found'}, status=404)

            old_file_path = image.file.path
            old_filename = image.filename

            print(f"Renaming from: {old_filename} to: {new_filename}")
            print(f"Old file path: {old_file_path}")

            # Validate that old file exists
            if not os.path.exists(old_file_path):
                return JsonResponse({
                    'error': f'Original file not found: {old_filename}'
                }, status=404)

            # Ensure the new filename has proper extension
            old_ext = os.path.splitext(old_filename)[1]
            new_ext = os.path.splitext(new_filename)[1]

            if not new_ext:
                new_filename += old_ext
            elif new_ext.lower() != old_ext.lower():
                return JsonResponse({
                    'error': f'Cannot change file extension from {old_ext} to {new_ext}'
                }, status=400)

            # Generate new file path
            file_dir = os.path.dirname(old_file_path)
            new_file_path = os.path.join(file_dir, new_filename)

            # Check if new filename already exists (and it's not the same file)
            if os.path.exists(new_file_path) and new_file_path != old_file_path:
                return JsonResponse({
                    'error': f'Filename already exists: {new_filename}'
                }, status=400)

            # Rename the file in storage
            try:
                os.rename(old_file_path, new_file_path)
                print(f"File renamed successfully on disk: {new_file_path}")
            except OSError as e:
                return JsonResponse({
                    'error': f'File system error: {str(e)}'
                }, status=500)

            # Update the file field to point to the new path
            from django.conf import settings
            media_root = settings.MEDIA_ROOT
            relative_new_path = os.path.relpath(new_file_path, media_root)

            # Update both filename AND file field
            image.filename = new_filename
            image.file.name = relative_new_path  # This updates the FileField path!

            # Re-extract values from new filename
            image.extract_values_from_filename()

            # Save the model (this updates both fields in database)
            image.save()

            print(f"Database updated - filename: {image.filename}, file field: {image.file.name}")

            return JsonResponse({
                'success': True,
                'message': 'Image renamed successfully',
                'new_filename': new_filename,
                'file_url': image.file.url  # Return the updated URL
            })

        except ReadingImage.DoesNotExist:
            return JsonResponse({'error': 'Image not found'}, status=404)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Unexpected error: {str(e)}'}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=400)


@csrf_exempt
def delete_reading(request, image_id):
    """Delete a reading image"""
    if request.method == 'DELETE':
        try:
            image = ReadingImage.objects.get(id=image_id)
            image.delete()
            return JsonResponse({'success': True, 'message': 'Image deleted successfully'})
        except ReadingImage.DoesNotExist:
            return JsonResponse({'error': 'Image not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=400)
