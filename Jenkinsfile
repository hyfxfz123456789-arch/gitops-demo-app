@NonCPS
def scanCounts(String jsonText) {
    def reports = new groovy.json.JsonSlurperClassic().parseText(jsonText)
    def report = reports['application/vnd.security.vulnerability.report; version=1.1']

    if (report == null || report.generated_at == null) {
        return null
    }

    def vulnerabilities = report.vulnerabilities ?: []
    int blocked = vulnerabilities.count {
        it.severity in ['Critical', 'High']
    }

    return [total: vulnerabilities.size(), blocked: blocked]
}

pipeline {
    agent {
        kubernetes {
            inheritFrom 'default'
            yaml '''
apiVersion: v1
kind: Pod
spec:
  imagePullSecrets:
    - name: harbor-pull
  nodeSelector:
    kubernetes.io/hostname: k8s-node-04
  containers:
    - name: buildah
      image: 192.168.119.166:8443/gitops-demo/buildah:stable
      imagePullPolicy: IfNotPresent
      command: ["cat"]
      tty: true
      securityContext:
        privileged: true
        runAsUser: 0
      env:
        - name: HTTP_PROXY
          value: http://192.168.1.5:10808
        - name: HTTPS_PROXY
          value: http://192.168.1.5:10808
        - name: NO_PROXY
          value: localhost,127.0.0.1,192.168.119.166,.svc,.cluster.local
      volumeMounts:
        - name: harbor-ca
          mountPath: /etc/containers/certs.d/192.168.119.166:8443
          readOnly: true
  volumes:
    - name: harbor-ca
      configMap:
        name: harbor-ca
        items:
          - key: ca.crt
            path: ca.crt
'''
        }
    }

    options {
        skipDefaultCheckout(true)
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.GIT_SHORT = sh(
                        script: 'git rev-parse --short HEAD',
                        returnStdout: true
                    ).trim()
                    env.IMAGE = "192.168.119.166:8443/gitops-demo/web:${BUILD_NUMBER}-${GIT_SHORT}"
                    echo "Git commit: ${GIT_SHORT}"
                    echo "Image: ${IMAGE}"
                }
                sh 'test -f app.py && test -f Dockerfile'
            }
        }

        stage('Build and Push') {
    when {
        anyOf {
            changeset pattern: 'app.py', comparator: 'EQUALS'
            changeset pattern: 'Dockerfile', comparator: 'EQUALS'
            changeset pattern: '.dockerignore', comparator: 'EQUALS'
        }
    }

    steps {
        container('buildah') {
            withCredentials([usernamePassword(
                credentialsId: 'harbor-jenkins-push',
                usernameVariable: 'HARBOR_USER',
                passwordVariable: 'HARBOR_PASS'
            )]) {
                sh '''
                    set +x
                    set -eu

                    trap 'rm -f /tmp/harbor-auth.json' EXIT

                    printf '%s' "$HARBOR_PASS" | buildah login \
                      --authfile /tmp/harbor-auth.json \
                      --username "$HARBOR_USER" \
                      --password-stdin \
                      192.168.119.166:8443

                    buildah --storage-driver=vfs bud \
                      --authfile /tmp/harbor-auth.json \
                      --isolation=chroot \
                      --pull=always \
                      --build-arg APP_VERSION="${BUILD_NUMBER}" \
                      --build-arg GIT_COMMIT="${GIT_SHORT}" \
                      -t "${IMAGE}" .

                    buildah --storage-driver=vfs push \
                      --authfile /tmp/harbor-auth.json \
                      "${IMAGE}"
                '''
            }
        }
    }
}
        stage('Harbor Scan Gate') {
            when {
                anyOf {
                    changeset pattern: 'app.py', comparator: 'EQUALS'
                    changeset pattern: 'Dockerfile', comparator: 'EQUALS'
                    changeset pattern: '.dockerignore', comparator: 'EQUALS'
                }
            }
            steps {
                script {
                    boolean scanCompleted = false

                    // 每 15 秒查询一次，最多查询 40 次。
                    for (int attempt = 1; attempt <= 40; attempt++) {
                        String status

                        container('buildah') {
                            withCredentials([usernamePassword(
                                credentialsId: 'harbor-jenkins-push',
                                usernameVariable: 'HARBOR_USER',
                                passwordVariable: 'HARBOR_PASS'
                            )]) {
                                status = sh(
                                    script: '''
                                        set +x
                                        TAG="${IMAGE##*:}"
                                        curl -sS \
                                          --cacert /etc/containers/certs.d/192.168.119.166:8443/ca.crt \
                                          -u "$HARBOR_USER:$HARBOR_PASS" \
                                          -H 'Accept: application/json' \
                                          -o harbor-scan.json \
                                          -w '%{http_code}' \
                                          "https://192.168.119.166:8443/api/v2.0/projects/gitops-demo/repositories/web/artifacts/${TAG}/additions/vulnerabilities" \
                                          || true
                                    ''',
                                    returnStdout: true
                                ).trim()
                            }
                        }

                        echo "Harbor scan query ${attempt}/40: HTTP ${status}"

                        if (status == '200') {
                            def counts = scanCounts(readFile('harbor-scan.json'))

                            if (counts == null) {
                                echo 'Harbor 已响应，但扫描报告尚未生成，继续等待'
                            } else {
                                echo "扫描完成：总漏洞 ${counts.total}，Critical/High ${counts.blocked}"

                                if (counts.blocked > 0) {
                                    error "镜像存在 ${counts.blocked} 项 Critical/High 漏洞，停止发布"
                                }

                                scanCompleted = true
                                break
                            }
                        }

                        if (status in ['401', '403']) {
                            error "Harbor API 权限验证失败：HTTP ${status}"
                        }

                        if (attempt < 40) {
                            sleep time: 15, unit: 'SECONDS'
                        }
                    }

                    if (!scanCompleted) {
                        error '等待 Harbor 扫描报告超时，停止发布'
                    }
                }
            }
        }

        stage('Update GitOps Repo') {
            when {
                anyOf {
                    changeset pattern: 'app.py', comparator: 'EQUALS'
                    changeset pattern: 'Dockerfile', comparator: 'EQUALS'
                    changeset pattern: '.dockerignore', comparator: 'EQUALS'
                }
            }
            steps {
                dir('gitops-demo-env') {
                    withCredentials([sshUserPrivateKey(
                        credentialsId: 'gitlab-env-write',
                        keyFileVariable: 'GITLAB_KEY'
                    )]) {
                        sh '''
                            set +x
                            set -eu

                            HOSTS_FILE=$(mktemp)
                            trap 'rm -f "$HOSTS_FILE"' EXIT
                            printf '%s\\n' '192.168.119.166 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILTvoNrOix9j2B1FYNQWwQtO4F7NLLWhFRtIzs2F7LVk' > "$HOSTS_FILE"
                            export GIT_SSH_COMMAND="ssh -i $GITLAB_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOSTS_FILE"

                            git clone --branch develop git@192.168.119.166:dev/gitops-demo-env.git .
                            sed -i "s/^  tag: .*/  tag: ${BUILD_NUMBER}-${GIT_SHORT}/" charts/gitops-demo/values-env.yaml
                            grep -Fx "  tag: ${BUILD_NUMBER}-${GIT_SHORT}" charts/gitops-demo/values-env.yaml

                            git add charts/gitops-demo/values-env.yaml
                            git -c user.name=Jenkins \
                                -c user.email=jenkins@lab.local \
                                commit -m "Deploy demo image ${BUILD_NUMBER}-${GIT_SHORT}"
                            git push origin develop
                        '''
                    }
                }
            }
        }
    }
}
