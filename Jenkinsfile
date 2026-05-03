pipeline {
    agent any

    stages {

        stage('Checkout') {
            steps {
                git 'https://github.com/Veom2-cloud/SmartBiz-ERP'
            }
        }

        stage('Install Dependencies') {
            steps {
                bat 'pip install -r requirements.txt'
            }
        }

        stage('Run Tests') {
            steps {
                bat 'pytest -v --cov=.'
            }
        }

    }
}