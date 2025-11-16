import click
import subprocess
import json
import re
import os

from pathlib import Path
from .boilerplates import *
from .utils import (
	create_file,
	add_commands_to_root_package_json,
	add_routing_rule_to_hooks,
)


class SPAGenerator:
	def __init__(self, framework, spa_name, app, add_tailwindcss, typescript, add_shadcn=False):
		"""Initialize a new SPAGenerator instance"""
		self.framework = framework
		self.app = app
		self.app_path = Path("../apps") / app
		self.spa_name = spa_name
		self.spa_path: Path = self.app_path / self.spa_name
		self.add_tailwindcss = add_tailwindcss
		self.use_typescript = typescript
		self.add_shadcn = add_shadcn

		self.validate_spa_name()

	def validate_spa_name(self):
		if self.spa_name == self.app:
			click.echo("Dashboard name must not be same as app name", err=True, color=True)
			exit(1)

	def generate_spa(self):
		click.echo("Generating spa...")
		if self.framework == "vue":
			self.initialize_vue_vite_project()
			self.link_controller_files()
			self.setup_proxy_options()
			self.setup_vue_vite_config()
			self.setup_vue_router()
			self.create_vue_files()

		elif self.framework == "react":
			self.initialize_react_vite_project()
			self.setup_proxy_options()
			self.setup_react_vite_config()
			self.create_react_files()
			self.create_env_files()
			self.create_python_context_file()
			self.update_index_html()
			
			if self.add_shadcn:
				self.setup_shadcn()

		# Common to all frameworks
		add_commands_to_root_package_json(self.app, self.spa_name)
		self.create_www_directory()

		if self.add_tailwindcss and self.framework == "vue":
			self.setup_tailwindcss_vue()

		add_routing_rule_to_hooks(self.app, self.spa_name)

		click.echo(f"Run: cd {self.spa_path.absolute().resolve()} && npm run dev")
		click.echo("to start the development server and visit: http://<site>:8080")

	def setup_tailwindcss_vue(self):
		# Install Tailwind v4 for Vue
		subprocess.run(
			[
				"npm",
				"install",
				"-D",
				"tailwindcss@latest",
				"@tailwindcss/vite@latest",
			],
			cwd=self.spa_path,
		)

		# Create index.css with Tailwind v4 syntax
		index_css_path: Path = self.spa_path / "src/index.css"
		create_file(index_css_path, INDEX_CSS_BOILERPLATE)

		# Update vite.config to include Tailwind plugin
		vite_config_path = self.spa_path / ("vite.config.ts" if self.use_typescript else "vite.config.js")
		content = vite_config_path.read_text()
		
		# Add tailwindcss import
		if "import tailwindcss from '@tailwindcss/vite'" not in content:
			content = content.replace(
				"import vue from '@vitejs/plugin-vue';",
				"import vue from '@vitejs/plugin-vue';\nimport tailwindcss from '@tailwindcss/vite';"
			)
			# Add to plugins array
			content = content.replace(
				"plugins: [vue()],",
				"plugins: [vue(), tailwindcss()],"
			)
			vite_config_path.write_text(content)

	def create_env_files(self):
		"""Create .env.local and .env.production files"""
		env_local_path = self.spa_path / ".env.local"
		env_production_path = self.spa_path / ".env.production"
		
		create_file(env_local_path, ENV_LOCAL_BOILERPLATE)
		create_file(
			env_production_path, 
			ENV_PRODUCTION_BOILERPLATE.replace("{{name}}", self.spa_name)
		)
		
		click.echo(click.style(
			f"\n⚠️  Important: Edit {env_local_path} and set VITE_SITE_NAME to your site name\n",
			fg="yellow"
		))

	def create_python_context_file(self):
		"""Create Python context file in www directory"""
		www_path = self.app_path / self.app / "www"
		context_file = www_path / f"{self.spa_name}.py"
		
		create_file(context_file, PYTHON_CONTEXT_BOILERPLATE)
		click.echo(f"Created context file: {context_file}")

	def update_index_html(self):
		"""Update index.html with boot data injection"""
		index_html_path = self.spa_path / "index.html"
		
		if index_html_path.exists():
			# Replace entire content with new template
			create_file(index_html_path, INDEX_HTML_BOILERPLATE)
		else:
			create_file(index_html_path, INDEX_HTML_BOILERPLATE)

	def setup_shadcn(self):
		"""Setup shadcn/ui for React with Tailwind v4"""
		click.echo("Setting up shadcn/ui...")
		
		# Install required dependencies
		subprocess.run(
			["npm", "install", "class-variance-authority", "clsx", "tailwind-merge"],
			cwd=self.spa_path,
		)
		
		# Create lib/utils.ts
		lib_dir = self.spa_path / "src/lib"
		lib_dir.mkdir(exist_ok=True)
		
		utils_content = """import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
"""
		create_file(lib_dir / "utils.ts", utils_content)
		
		# Create components.json
		create_file(self.spa_path / "components.json", COMPONENTS_JSON_BOILERPLATE)
		
		# Update tsconfig files
		self.update_tsconfig_for_shadcn()
		
		click.echo(click.style(
			"\n✓ shadcn/ui setup complete!\n"
			"  Run: npx shadcn@latest add button\n"
			"  to add your first component\n",
			fg="green"
		))

	def update_tsconfig_for_shadcn(self):
		"""Update tsconfig.json and tsconfig.app.json for path aliases"""
		
		def clean_json_comments(content):
			"""Remove comments and trailing commas from JSON-like content"""
			# Remove single-line comments
			content = re.sub(r'//.*', '', content)
			# Remove multi-line comments
			content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
			# Remove trailing commas before closing braces/brackets
			content = re.sub(r',(\s*[}\]])', r'\1', content)
			return content
		
		# Update tsconfig.json
		tsconfig_path = self.spa_path / "tsconfig.json"
		if not tsconfig_path.exists():
			create_file(tsconfig_path, TSCONFIG_JSON_BOILERPLATE)
		else:
			try:
				with tsconfig_path.open("r") as f:
					content = f.read()
				cleaned_content = clean_json_comments(content)
				tsconfig = json.loads(cleaned_content)
				
				if "compilerOptions" not in tsconfig:
					tsconfig["compilerOptions"] = {}
				
				tsconfig["compilerOptions"]["baseUrl"] = "."
				tsconfig["compilerOptions"]["paths"] = {"@/*": ["./src/*"]}
				
				with tsconfig_path.open("w") as f:
					json.dump(tsconfig, f, indent=2)
			except json.JSONDecodeError as e:
				click.echo(f"Warning: Could not parse tsconfig.json: {e}")
				click.echo("Creating new tsconfig.json")
				create_file(tsconfig_path, TSCONFIG_JSON_BOILERPLATE)
		
		# Update tsconfig.app.json
		tsconfig_app_path = self.spa_path / "tsconfig.app.json"
		if tsconfig_app_path.exists():
			try:
				with tsconfig_app_path.open("r") as f:
					content = f.read()
				cleaned_content = clean_json_comments(content)
				tsconfig_app = json.loads(cleaned_content)
				
				if "compilerOptions" not in tsconfig_app:
					tsconfig_app["compilerOptions"] = {}
				
				tsconfig_app["compilerOptions"]["baseUrl"] = "."
				tsconfig_app["compilerOptions"]["paths"] = {"@/*": ["./src/*"]}
				
				with tsconfig_app_path.open("w") as f:
					json.dump(tsconfig_app, f, indent=2)
			except json.JSONDecodeError as e:
				click.echo(f"Warning: Could not parse tsconfig.app.json: {e}")
				# Create a basic tsconfig.app.json with the needed config
				create_file(tsconfig_app_path, TSCONFIG_APP_JSON_BOILERPLATE)

	def create_vue_files(self):
		app_vue = self.spa_path / "src/App.vue"
		create_file(app_vue, APP_VUE_BOILERPLATE)

		views_dir: Path = self.spa_path / "src/views"
		if not views_dir.exists():
			views_dir.mkdir()

		home_vue = views_dir / "Home.vue"
		login_vue = views_dir / "Login.vue"

		create_file(home_vue, HOME_VUE_BOILERPLATE)
		create_file(login_vue, LOGIN_VUE_BOILERPLATE)

	def setup_vue_router(self):
		# Setup vue router
		router_dir_path: Path = self.spa_path / "src/router"

		# Create router directory
		router_dir_path.mkdir()

		# Create files
		router_index_file = router_dir_path / "index.js"
		create_file(
			router_index_file, ROUTER_INDEX_BOILERPLATE.replace("{{name}}", self.spa_name)
		)

		auth_routes_file = router_dir_path / "auth.js"
		create_file(auth_routes_file, AUTH_ROUTES_BOILERPLATE)

	def initialize_vue_vite_project(self):
		# Run "yarn create vite {name} --template vue"
		print("Scafolding vue project...")
		if self.use_typescript:
			subprocess.run(
				["yarn", "create", "vite", self.spa_name, "--template", "vue-ts"], cwd=self.app_path
			)
		else:
			subprocess.run(
				["yarn", "create", "vite", self.spa_name, "--template", "vue"], cwd=self.app_path
			)

		# Install router and other npm packages
		# yarn add vue-router@4 socket.io-client@4.5.1
		print("Installing dependencies...")
		subprocess.run(
			["yarn", "add", "vue-router@^4", "socket.io-client@^4.5.1"], cwd=self.spa_path
		)

	def link_controller_files(self):
		# Link controller files in main.js/main.ts
		print("Linking controller files...")
		main_js: Path = self.app_path / (
			f"{self.spa_name}/src/main.ts"
			if self.use_typescript
			else f"{self.spa_name}/src/main.js"
		)

		if main_js.exists():
			with main_js.open("w") as f:
				boilerplate = MAIN_JS_BOILERPLATE

				# Add css import
				if self.add_tailwindcss:
					boilerplate = "import './index.css';\n" + boilerplate

				f.write(boilerplate)
		else:
			click.echo("src/main.js not found!")
			return

	def setup_proxy_options(self):
		# Setup proxy options file
		proxy_options_file: Path = self.spa_path / (
			"proxyOptions.ts" if self.use_typescript else "proxyOptions.js"
		)
		create_file(proxy_options_file, PROXY_OPTIONS_BOILERPLATE)

	def setup_vue_vite_config(self):
		vite_config_file: Path = self.spa_path / (
			"vite.config.ts" if self.use_typescript else "vite.config.js"
		)
		if not vite_config_file.exists():
			vite_config_file.touch()
		with vite_config_file.open("w") as f:
			boilerplate = VUE_VITE_CONFIG_BOILERPLATE.replace("{{app}}", self.app)
			boilerplate = boilerplate.replace("{{name}}", self.spa_name)
			f.write(boilerplate)

	def create_www_directory(self):
		www_dir_path: Path = self.app_path / f"{self.app}/www"

		if not www_dir_path.exists():
			www_dir_path.mkdir()

	def initialize_react_vite_project(self):
		# Run "yarn create vite {name} --template react"
		print("Scaffolding React project...")
		if self.use_typescript:
			subprocess.run(
				["yarn", "create", "vite", self.spa_name, "--template", "react-ts"],
				cwd=self.app_path,
				env={**os.environ, "YARN_ENABLE_IMMUTABLE_INSTALLS": "false"}
			)
		else:
			subprocess.run(
				["yarn", "create", "vite", self.spa_name, "--template", "react"], 
				cwd=self.app_path,
				env={**os.environ, "YARN_ENABLE_IMMUTABLE_INSTALLS": "false"}
			)

		# Install dependencies
		print("Installing dependencies...")
		
		# Base dependencies
		base_deps = ["frappe-react-sdk"]
		
		# Tailwind v4 dependencies
		if self.add_tailwindcss:
			base_deps.extend(["tailwindcss@next", "@tailwindcss/vite"])
		
		subprocess.run(["yarn", "add"] + base_deps, cwd=self.spa_path)
		
		# Dev dependencies
		subprocess.run(
			["yarn", "add", "-D", "@types/node"],
			cwd=self.spa_path
		)

	def setup_react_vite_config(self):
		vite_config_file: Path = self.spa_path / (
			"vite.config.ts" if self.use_typescript else "vite.config.js"
		)
		if not vite_config_file.exists():
			vite_config_file.touch()
		with vite_config_file.open("w") as f:
			boilerplate = REACT_VITE_CONFIG_BOILERPLATE.replace("{{app}}", self.app)
			boilerplate = boilerplate.replace("{{name}}", self.spa_name)
			f.write(boilerplate)

	def create_react_files(self):
		# Create index.css with Tailwind v4
		if self.add_tailwindcss:
			index_css_path = self.spa_path / "src/index.css"
			create_file(index_css_path, INDEX_CSS_BOILERPLATE)
		
		# Create App component
		app_react = self.spa_path / ("src/App.tsx" if self.use_typescript else "src/App.jsx")
		create_file(app_react, APP_REACT_BOILERPLATE)