#!/usr/bin/env bash

function install_conda {
	# This function has been heavily inspired by Invisible Cities (next-exp/IC on github).

	# Conda installation for MacOS and Linux
	case "$(uname -s)" in	
	       Darwin)
	           export CONDA_OS=MacOSX
	           ;;	
	       Linux)
	           export CONDA_OS=Linux
	           ;;
			*)
				echo Installation only support on MacOS and Linux.;
				exit 1;;
	esac

	# Setting architecture based on input
	CONDA_ARCH=$(uname -m)
	
	case $CONDA_ARCH in
		x86_64) : ;;
		arm64)  : ;;	
		aarch64) : ;;
		*)
			echo "Installation only supported on x86_64 and arm architectures"
			exit 1
			;;
	esac

	echo Installing conda for $CONDA_OS on $CONDA_ARCH architecture
	CONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-py${PYTHON_VERSION//.}_24.9.2-0-${CONDA_OS}-${CONDA_ARCH}.sh"
	if which wget; then
        wget ${CONDA_URL} -O miniconda.sh
    else
        curl ${CONDA_URL} -o miniconda.sh
    fi
    bash miniconda.sh -b -p $HOME/miniconda
	CONDA_SH=$HOME/miniconda/etc/profile.d/conda.sh
	source $CONDA_SH
	eval "$(conda shell.bash hook)"
	conda init bash >/dev/null 2>&1 || true
	echo Activated conda by sourcing $CONDA_SH
}	


echo "SQUID - This acronym means something"

PYTHON_VERSION='3.12'
DATE='10-24'
# set env name
SQUID_ENV_NAME=SQUID-${PYTHON_VERSION}-${DATE}


# CHECK THAT XERYONS INSTALLED LOCALLY (i havent dont this)
#wget https://xeryon.com/download-files/Xeryon%20Python-Matlab%20Library.zip -O lib/Xeryon_libs.zip
# then extract libraries into folder
#mkdir -pv lib/Xeryon
#unzip lib/Xeryon_libs.zip -d lib/Xeryon
# this can now be called by lib.Xeryon in python



# set directory path to variable
export SQUID_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# setup environment variables
export PATH=$SQUID_DIR/bin:$PATH


# logo ex. echo "$(<${MULE_DIR}/assets/MULE.txt)"

echo "Identified directory: $SQUID_DIR"

if conda --version ; then
	echo Initialising Conda...
	CONDA_BASE=$(conda info --base 2>/dev/null)
	if [ -n "$CONDA_BASE" ] && [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
		source "$CONDA_BASE/etc/profile.d/conda.sh"
		eval "$(conda shell.bash hook)"
		conda init bash >/dev/null 2>&1 || true
	else
		conda init bash >/dev/null 2>&1 || true
	fi
else
	echo "No Conda installation detected, installing conda."
	echo 'Download conda? Select [1/2]:'
	select yn in Yes No; do
		case $yn in
			Yes ) install_conda; break;;
			No ) echo "SQUID activation aborted"; return;;
		esac
	done
fi

# If conda environment exists, activate it. Otherwise create it
if ! (conda env list | grep ${SQUID_ENV_NAME}) >> /dev/null
then
	echo "Couldn't find environment, creating environment..."
	conda env create -f SQUID_environment.yml
fi

echo "Activating environment..."
if [ -n "$CI" ]; then
	echo "CI detected, skipping conda activate. Use 'conda run -n ${SQUID_ENV_NAME} ...'"
else
	conda activate ${SQUID_ENV_NAME}
fi

cd ${SQUID_DIR}

