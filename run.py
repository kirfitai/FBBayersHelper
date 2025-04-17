from app import create_app, db
from app.models.user import User
from app.models.setup import Setup, ThresholdEntry, CampaignSetup
from app.models.token import FacebookToken
import os

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'User': User,
        'Setup': Setup,
        'ThresholdEntry': ThresholdEntry,
        'CampaignSetup': CampaignSetup,
        'FacebookToken': FacebookToken
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)