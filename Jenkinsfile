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

@NonCPS
def parseReleaseRecord(String jsonText) {
    def data = new groovy.json.JsonSlurperClassic().parseText(jsonText)
    return [
        sourceChangeCommit: data.sourceChangeCommit?.toString(),
        buildInputFingerprint: data.buildInputFingerprint?.toString(),
        imageTag: data.imageTag?.toString(),
        imageDigest: data.imageDigest?.toString()
    ]
}

@NonCPS
def promotionMrUrls(String jsonText) {
    def data = new groovy.json.JsonSlurperClassic().parseText(jsonText)

    if (data instanceof List) {
        return data.collect { it.web_url?.toString() }.findAll { it }
    }

    return data.web_url ? [data.web_url.toString()] : []
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
    - name: python-test
      image: 192.168.119.166:8443/gitops-demo/python-base:3.13.18-alpine
      imagePullPolicy: IfNotPresent
      command: ["cat"]
      tty: true
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

                    env.BUILD_COMMIT = sh(
                        script: 'git rev-parse HEAD',
                        returnStdout: true
                    ).trim()

                    env.SOURCE_CHANGE_COMMIT = sh(
                        script: 'git log -1 --format=%H -- app.py Dockerfile .dockerignore',
                        returnStdout: true
                    ).trim()

                    env.BUILD_INPUT_FINGERPRINT = sh(
                        script: "git ls-tree HEAD -- app.py Dockerfile .dockerignore | sha256sum | cut -d ' ' -f1",
                        returnStdout: true
                    ).trim()

                    env.IMAGE = "192.168.119.166:8443/gitops-demo/web:${BUILD_NUMBER}-${GIT_SHORT}"

                    echo "Build commit: ${BUILD_COMMIT}"
                    echo "Source change commit: ${SOURCE_CHANGE_COMMIT}"
                    echo "Build input fingerprint: ${BUILD_INPUT_FINGERPRINT}"
                    echo "Image tag: ${IMAGE}"
                }

                sh 'test -f app.py && test -f Dockerfile && test -f .dockerignore'
            }
        }
        
        stage('Test') {
            steps {
                container('python-test') {
                    sh 'python -m unittest discover -s tests -v'
                }
            }
        }

        stage('Build and Push') {
            when {
                allOf {
                    branch 'develop'
                    anyOf {
                        changeset pattern: 'app.py', comparator: 'EQUALS'
                        changeset pattern: 'Dockerfile', comparator: 'EQUALS'
                        changeset pattern: '.dockerignore', comparator: 'EQUALS'
                    }
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
                              --digestfile "$WORKSPACE/image.digest" \
                              "${IMAGE}"
                        '''
                    }

                    script {
                        env.IMAGE_DIGEST = readFile('image.digest').trim()

                        if (!(env.IMAGE_DIGEST ==~ /sha256:[0-9a-f]{64}/)) {
                            error "Harbor 返回的镜像 digest 无效：${env.IMAGE_DIGEST}"
                        }

                        echo "Pushed image digest: ${env.IMAGE_DIGEST}"
                    }
                }
            }
        }
       
        stage('Image Smoke Test') {
            when {
                allOf {
                    branch 'develop'
                    anyOf {
                        changeset pattern: 'app.py', comparator: 'EQUALS'
                        changeset pattern: 'Dockerfile', comparator: 'EQUALS'
                        changeset pattern: '.dockerignore', comparator: 'EQUALS'
                    }
                }
            }

            steps {
                container('buildah') {
                    sh '''
                        set -eu

                        TEST_CONTAINER=$(buildah --storage-driver=vfs from "$IMAGE")
                        trap 'buildah --storage-driver=vfs rm "$TEST_CONTAINER" >/dev/null' EXIT

                        buildah --storage-driver=vfs copy \
                          "$TEST_CONTAINER" tests/smoke_image.py /tmp/smoke_image.py

                        buildah --storage-driver=vfs run \
                          --isolation=chroot \
                          "$TEST_CONTAINER" -- \
                          python /tmp/smoke_image.py "$BUILD_NUMBER" "$GIT_SHORT"
                    '''
                }
            }
        }

        stage('Harbor Scan Gate') {
            when {
                allOf {
                    branch 'develop'
                    anyOf {
                        changeset pattern: 'app.py', comparator: 'EQUALS'
                        changeset pattern: 'Dockerfile', comparator: 'EQUALS'
                        changeset pattern: '.dockerignore', comparator: 'EQUALS'
                    }
                }
            }

            steps {
                script {
                    boolean scanCompleted = false

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
                allOf {
                    branch 'develop'
                    anyOf {
                        changeset pattern: 'app.py', comparator: 'EQUALS'
                        changeset pattern: 'Dockerfile', comparator: 'EQUALS'
                        changeset pattern: '.dockerignore', comparator: 'EQUALS'
                    }
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

                            printf '%s\\n' \
                              '192.168.119.166 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILTvoNrOix9j2B1FYNQWwQtO4F7NLLWhFRtIzs2F7LVk' \
                              > "$HOSTS_FILE"

                            export GIT_SSH_COMMAND="ssh -i $GITLAB_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOSTS_FILE"

                            git clone --branch develop \
                              git@192.168.119.166:dev/gitops-demo-env.git .

                            VALUES_FILE=charts/gitops-demo/values-env.yaml

                            sed -i \
                              "s/^  tag: .*/  tag: ${BUILD_NUMBER}-${GIT_SHORT}/" \
                              "$VALUES_FILE"

                            sed -i '/^  digest: /d' "$VALUES_FILE"

                            sed -i \
                              "/^  tag: /a\\  digest: ${IMAGE_DIGEST}" \
                              "$VALUES_FILE"

                            grep -Fx \
                              "  tag: ${BUILD_NUMBER}-${GIT_SHORT}" \
                              "$VALUES_FILE"

                            grep -Fx \
                              "  digest: ${IMAGE_DIGEST}" \
                              "$VALUES_FILE"

                            mkdir -p releases/by-source
                            RECORD="releases/by-source/${SOURCE_CHANGE_COMMIT}.json"

                            cat > "$RECORD" <<EOF
{
  "sourceChangeCommit": "${SOURCE_CHANGE_COMMIT}",
  "buildCommit": "${BUILD_COMMIT}",
  "buildInputFingerprint": "${BUILD_INPUT_FINGERPRINT}",
  "imageTag": "${IMAGE}",
  "imageDigest": "${IMAGE_DIGEST}"
}
EOF

                            git add "$VALUES_FILE" "$RECORD"

                            git -c user.name=Jenkins \
                                -c user.email=jenkins@lab.local \
                                commit -m "Deploy verified image ${BUILD_NUMBER}-${GIT_SHORT}"

                            git push origin develop
                        '''
                    }
                }
            }
        }
            stage('Verify Production Candidate') {
            when {
                branch 'main'
            }

            steps {
                dir('gitops-promotion-check') {
                    withCredentials([sshUserPrivateKey(
                        credentialsId: 'gitlab-env-write',
                        keyFileVariable: 'GITLAB_KEY'
                    )]) {
                        sh '''
                            set +x
                            set -eu

                            HOSTS_FILE=$(mktemp)
                            trap 'rm -f "$HOSTS_FILE"' EXIT

                            printf '%s\\n' \
                              '192.168.119.166 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILTvoNrOix9j2B1FYNQWwQtO4F7NLLWhFRtIzs2F7LVk' \
                              > "$HOSTS_FILE"

                            export GIT_SSH_COMMAND="ssh -i $GITLAB_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOSTS_FILE"

                            git clone --depth 1 --branch develop \
                              git@192.168.119.166:dev/gitops-demo-env.git .

                            RECORD="releases/by-source/${SOURCE_CHANGE_COMMIT}.json"
                            test -f "$RECORD" || {
                                echo "找不到开发环境的已验证镜像记录：$RECORD"
                                exit 1
                            }
                        '''
                    }

                    script {
                        String recordPath =
                            "releases/by-source/${env.SOURCE_CHANGE_COMMIT}.json"

                        def record = parseReleaseRecord(readFile(recordPath))
 
                        if (record.sourceChangeCommit != env.SOURCE_CHANGE_COMMIT) {
                            error '发布记录中的源码提交与 main 不一致'
                        }

                        if (record.buildInputFingerprint != env.BUILD_INPUT_FINGERPRINT) {
                            error 'main 的构建输入与已验证镜像不一致，停止晋级'
                        }

                        if (!(record.imageDigest ==~ /sha256:[0-9a-f]{64}/)) {
                            error '发布记录中的镜像 digest 无效'
                        }

                        String imagePrefix = '192.168.119.166:8443/gitops-demo/web:'
			if (!record.imageTag.startsWith(imagePrefix) ||
			    !(record.imageTag.substring(imagePrefix.length()) ==~ /[0-9]+-[0-9a-f]+/)) {
			    error '发布记录中的镜像标签不符合预期'
			}

                        env.PROMOTE_IMAGE_TAG = record.imageTag
                        env.PROMOTE_IMAGE_DIGEST = record.imageDigest

                        echo "已验证生产候选镜像：${env.PROMOTE_IMAGE_TAG}"
                        echo "镜像 digest：${env.PROMOTE_IMAGE_DIGEST}"
                    }
                }
            }
        }
        
                stage('Create Production MR') {
            when {
                branch 'main'
            }

            steps {
                script {
                    if (!env.PROMOTE_IMAGE_TAG || !env.PROMOTE_IMAGE_DIGEST) {
                        error '生产候选镜像尚未通过验证'
                    }

                    env.PROMOTION_BRANCH =
                        "promote/${env.BUILD_COMMIT.substring(0, 12)}-" +
                        env.PROMOTE_IMAGE_DIGEST.substring(7, 19)

                    dir('gitops-production-mr') {
                        withCredentials([sshUserPrivateKey(
                            credentialsId: 'gitlab-env-write',
                            keyFileVariable: 'GITLAB_KEY'
                        )]) {
                            sh '''
                                set +x
                                set -eu

                                HOSTS_FILE=$(mktemp)
                                trap 'rm -f "$HOSTS_FILE"' EXIT

                                printf '%s\\n' \
                                  '192.168.119.166 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILTvoNrOix9j2B1FYNQWwQtO4F7NLLWhFRtIzs2F7LVk' \
                                  > "$HOSTS_FILE"

                                export GIT_SSH_COMMAND="ssh -i $GITLAB_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOSTS_FILE"

                                git clone --depth 1 --branch main \
                                  git@192.168.119.166:dev/gitops-demo-env.git .

                                VALUES_FILE=charts/gitops-demo/values-env.yaml
                                IMAGE_TAG="${PROMOTE_IMAGE_TAG##*:}"

                                sed -i \
                                  "s/^  tag: .*/  tag: ${IMAGE_TAG}/" \
                                  "$VALUES_FILE"

                                sed -i '/^  digest: /d' "$VALUES_FILE"

                                sed -i \
                                  "/^  tag: /a\\  digest: ${PROMOTE_IMAGE_DIGEST}" \
                                  "$VALUES_FILE"

                                grep -Fx "  tag: ${IMAGE_TAG}" "$VALUES_FILE"
                                grep -Fx "  digest: ${PROMOTE_IMAGE_DIGEST}" "$VALUES_FILE"

                                if git diff --quiet -- "$VALUES_FILE"; then
                                    touch .promotion-no-change
                                    echo '生产配置已经使用该镜像，无需创建 MR'
                                else
                                    git switch -c "$PROMOTION_BRANCH"
                                    git add "$VALUES_FILE"
                                    git -c user.name=Jenkins \
                                        -c user.email=jenkins@lab.local \
                                        commit -m "Promote verified image ${IMAGE_TAG}"

                                    if git ls-remote --heads origin "$PROMOTION_BRANCH" |
                                       grep -q .; then
                                        echo '候选分支已存在，检查已有 MR'
                                    else
                                        git push origin "$PROMOTION_BRANCH"
                                    fi
                                fi
                            '''
                        }

                        if (fileExists('.promotion-no-change')) {
                            echo '生产环境已是目标镜像，跳过创建 MR'
                            return
                        }

                        container('buildah') {
                            withCredentials([string(
                                credentialsId: 'gitlab-env-mr-api',
                                variable: 'GITLAB_API_TOKEN'
                            )]) {
                                sh '''
                                    set +x
                                    set -eu

                                    API='https://192.168.119.166/api/v4/projects/dev%2Fgitops-demo-env/merge_requests'
                                    CA='/etc/containers/certs.d/192.168.119.166:8443/ca.crt'

                                    curl -fsS --cacert "$CA" \
                                      --header "PRIVATE-TOKEN: $GITLAB_API_TOKEN" \
                                      --get \
                                      --data-urlencode 'state=opened' \
                                      --data-urlencode "source_branch=$PROMOTION_BRANCH" \
                                      --data-urlencode 'target_branch=main' \
                                      "$API" > promotion-mrs.json
                                '''
                            }
                        }

                        def existing = promotionMrUrls(
                            readFile('promotion-mrs.json')
                        )

                        if (existing) {
                            echo "生产晋级 MR 已存在：${existing[0]}"
                            return
                        }

                        container('buildah') {
                            withCredentials([string(
                                credentialsId: 'gitlab-env-mr-api',
                                variable: 'GITLAB_API_TOKEN'
                            )]) {
                                sh '''
                                    set +x
                                    set -eu

                                    API='https://192.168.119.166/api/v4/projects/dev%2Fgitops-demo-env/merge_requests'
                                    CA='/etc/containers/certs.d/192.168.119.166:8443/ca.crt'
                                    IMAGE_TAG="${PROMOTE_IMAGE_TAG##*:}"

                                    curl -fsS --cacert "$CA" \
                                      --header "PRIVATE-TOKEN: $GITLAB_API_TOKEN" \
                                      --request POST \
                                      --data-urlencode "source_branch=$PROMOTION_BRANCH" \
                                      --data-urlencode 'target_branch=main' \
                                      --data-urlencode "title=Promote verified web ${IMAGE_TAG} to production" \
                                      --data-urlencode "description=Verified image: ${PROMOTE_IMAGE_TAG}%0ADigest: ${PROMOTE_IMAGE_DIGEST}%0AApp commit: ${BUILD_COMMIT}" \
                                      "$API" > promotion-created.json
                                '''
                            }
                        }

                        def created = promotionMrUrls(
                            readFile('promotion-created.json')
                        )

                        if (!created) {
                            error 'GitLab 没有返回新建 MR 的地址'
                        }

                        echo "请审核并合并 GitOps 生产 MR：${created[0]}"
                    }
                }
            }
        }
    }
}
