from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user, login_required
from .. import db
from ..models import Video

videos_bp = Blueprint('videos', __name__, url_prefix='/')


@videos_bp.route('/')
def home():
    page = request.args.get('page', 1, type=int)
    videos = Video.query.filter_by(is_public=True).paginate(page=page, per_page=12)
    return render_template('home.html', videos=videos)


@videos_bp.route('/video/<int:video_id>')
def watch(video_id):
    video = Video.query.get_or_404(video_id)
    video.views += 1
    db.session.commit()
    return render_template('watch.html', video=video)


@videos_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        file_url = request.form.get('file_url')  # For now, just a URL
        
        video = Video(
            title=title,
            description=description,
            file_url=file_url,
            owner_id=current_user.id
        )
        db.session.add(video)
        db.session.commit()
        
        return jsonify({"message": "Video uploaded"}), 201
    
    return render_template('upload.html')


@videos_bp.route('/api/videos')
def get_videos():
    videos = Video.query.filter_by(is_public=True).all()
    return jsonify([{
        'id': v.id,
        'title': v.title,
        'views': v.views,
        'created_at': v.created_at.isoformat()
    } for v in videos])
