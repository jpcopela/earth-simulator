#version 400

layout(location = 0) in vec3 position;
layout(location = 1) in vec2 tex_coord;

uniform mat4 projection;
uniform mat4 view;

out vec2 texCoord;
out vec3 vertexCoord;

void main()
{   
    texCoord = tex_coord;
    vertexCoord = position;

    gl_Position = projection * view * vec4(position, 1.0);
}