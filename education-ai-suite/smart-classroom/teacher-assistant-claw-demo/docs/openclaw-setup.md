# OpenClaw setup for Teacher Assistant demo

The OpenClaw based agent functions as the "Teacher Assistant" persona that enables the staff of a school, which includes teachers, to create their own custom report based on the per classroom data provided by the Smart Classroom application. The custom report can be at a class level or at a grade level combining all classrooms in that grade and at the school level which combines all the grades. The deployment setup envisaged is shown in the figure below.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Teacher Assistant Demo                        │
│  ┌──────────┐     ┌─────────────────┐    ┌──────────────────────┐    │
│  │   SC-1   │◄───►| OpenClaw Agent  │◄──►│       Telegram       │    │
│  └──────────┘     │                 │    │ Channel based comms  |    │   
│  ┌──────────┐     │                 │    └──────────────────────┘    │
│  │   SC-2   │◄───►│                 │                                │
│  └──────────┘     │                 │    ┌──────────────────────┐    │
│  ┌──────────┐     │                 │───►|      OVMS local      |    │
│  |   SC-n   │◄───►│                 │    |       inference      |    │
│  └──────────┘     └─────────────────┘    └──────────────────────┘    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

```
Note: In the figure, Smart Classroom is abbreviated as SC.

## Pre-requisites

### System Requirements for OpenClaw agent
- Ubuntu 24.04 LTS
- Intel PTL based system 
- At least 32GB RAM
- 100GB free disk space for models and environments

### Smart Classroom setup
It is assumed here that Smart Classroom application is setup in a separate node compared to OpenClaw Agent. The WSL route of installing OpenClaw in a Windows environment and hence sharing the same compute resources with Smart Classroom app is not covered in this version. The set-up of the Smart Classroom is as per the documentation provided in the Smart Classroom application repo. This documentation is not repeated here. Communication between the Smart Classroom app and OpenClaw is covered in this documentation.

### Prepare for setup
- Docker engine installed and running
- Install curl, homebrew, and git as follows:
  ``` bash
    sudo apt update
    sudo apt upgrade -y
    sudo apt install -y build-essential curl git procps
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
    echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"' >> ~/.bashrc
  ```

## Setup OVMS
OVMS should be setup before OpenClaw installation to ensure easy discoverability and configuration. The OVMS setup is done with the following simple steps.

``` bash
mkdir -p $(pwd)/models
docker run --user $(id -u):$(id -g) -d \
       --device /dev/dri \
       --group-add=$(stat -c "%g" /dev/dri/render* | head -n 1) \
       --rm -p 8000:8000 \
       -v $(pwd)/models:/models:rw \
       openvino/model_server:latest-gpu \
       --source_model OpenVINO/Qwen3-8B-int4-ov \
       --model_repository_path models \
       --task text_generation \
       --rest_port 8000 \
       --target_device GPU
```
Verify OVMS is running using the following command
``` bash
curl http://localhost:8000/v3/models
```

## Setup Telegram


## Setup OpenClaw

### Step 1: OpenClaw installation
It is recommended to follow the standard OpenClaw documentation. Following command installs OpenClaw along with a few other dependencies specific to OpenClaw. This instruction is temporarily provided here as eventually the official documentation is recommended.

``` bash
curl -fsSL --proto '=https' --tlsv1.2 https://openclaw.ai/install.sh | bash -s -- --install-method npm --version 2026.6.6 --no-onboard
```

### Step 2: Configure OpenClaw
TODO: Add screenshots

Apply the pre-configured settings using the provided config file:

``` bash
openclaw config patch --file ./openclaw-config.json
```

<details> <summary>Alternativelly configure OpenClaw interactively.</summary>

The step 1 leads to OpenClaw onboarding process. Follow the steps listed below.
1. Read the security warning and press the left arrow key to navigate to Yes and hit Enter to continue. Hit enter again to select Quick Start.
2. Press the down arrow key to scroll down to "more" and hit Enter to expand the list, then continue scrolling down to "Custom Provider" and hit Enter.
3. Provide the OVMS link for API base URL: `http://127.0.0.1:8000/v3`
4. Press enter on API key.
5. Select `OpenAI` for end point compatibility. (TODO: Provide exact field name)
6. Enter the following for Model ID: `OpenVINO/Qwen3-8B-int4-ov`. This should give `verification successful` message on the screen. If not, go back to #3.
7. For Model Alias, enter a name of your choice. Example, `Qwen3-ovms`
8. Select the communication channel for your bot. Select `Telegram` for this use case.
9. Enter your Telegram bot token. On the screen, you should see instructions like:
   ``` bash
   Telegram bot token
    1) Open Telegram and chat with @BotFather
    2) Run /newbot (or /mybots)
    3) Copy the token (looks like 123456:ABC...)
   ```
   Todo: Link to the telegram documentation which should provide details on generating token, setting up bot etc.
10. Configure the web search API provider. TODO: Update. For now, select Duckduck Go.
11. Add the required skills. Select blogwatcher, nanopdf, clawhub (select npm), and github.
12. Skip the hooks configuration. TODO: revisit.
13. Hatch your claw in the terminal

</details>

## Learn More

- [OpenClaw]()
- [Smart Classroom]()
